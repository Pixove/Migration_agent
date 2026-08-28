from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.config import VALID_IMPACT_LEVELS, AppConfig
from agent.context_loader import build_document_index, build_red_lines
from agent.dispatcher import ToolDispatcher
from agent.guardrails import Budget, GuardrailError, build_guardrails
from agent.llm import (
    LLMClient,
    LLMError,
    create_llm_client,
    parse_json_object,
)
from agent.state import AuditWorkspace, MigrationState, Phase, PlanItem
from agent.tooling import ToolContext, register_tools
from agent.review import review_edit
from migration.registry import load_profile
from migration.scan_signals import scan_python_signals
from retrieval import HybridRetriever
from retrieval.knowledge_base import KnowledgeBase
from tools.patcher import apply_plan_item
from tools.reporter import write_report as generate_report

DEFAULT_MAX_AGENT_ITERATIONS = 20
MAX_HISTORY_MESSAGES = 24
DIRECTED_REPAIR_ATTEMPTS_PER_SIGNAL = 2
MAX_DIRECTED_REPAIR_TURNS = 20

READ_ONLY_ACTIONS = ("read_document", "read_source", "retrieve_examples")
EXECUTE_ACTIONS = (
    "propose_plan",
    "propose_edit",
    "apply_patch",
    "apply_edit",
    "run_verifier",
)

TOOL_DESCRIPTIONS = [
    {"name": "scan_files", "description": "扫描输入项目，返回文件清单", "params": {}},
    {
        "name": "retrieve_examples",
        "description": "从知识库检索迁移范例",
        "params": {"query": "string", "top_k": "integer（可选）"},
    },
    {
        "name": "propose_plan",
        "description": "生成迁移计划",
        "params": {"files": "list[string]（可选，默认全部）"},
    },
    {
        "name": "apply_patch",
        "description": "应用计划条目",
        "params": {"item": "object"},
    },
    {
        "name": "run_verifier",
        "description": "验证输出文件",
        "params": {"path": "string"},
    },
    {"name": "write_report", "description": "生成迁移报告", "params": {}},
    {
        "name": "read_document",
        "description": "按需读取规则/技能/文档",
        "params": {"path": "string", "max_chars": "integer（可选）"},
    },
    {
        "name": "propose_edit",
        "description": "生成语义编辑 diff 预览（不写文件）",
        "params": {
            "item": "object（字段：file, start_line, end_line, "
            "new_content 或 replacement, evidence, impact；"
            "缺省行范围时整文件替换）"
        },
    },
    {
        "name": "apply_edit",
        "description": "应用语义编辑到输出目录",
        "params": {
            "item": "object（字段：file, start_line, end_line, "
            "new_content 或 replacement, evidence, impact；"
            "缺省行范围时整文件替换）"
        },
    },
    {
        "name": "read_source",
        "description": "按需读取输入项目源文件",
        "params": {"path": "string", "max_chars": "integer（可选）"},
    },
]


class AgenticRunner:
    """LLM 工具决策循环：模型自主调用白名单工具，harness 负责把关。"""

    def __init__(
        self,
        config: AppConfig,
        source: str | Path,
        output: str | Path,
        *,
        docs: list[str | Path] | None = None,
        auto_approve: bool = False,
        llm: LLMClient | None = None,
        reviewer: Callable[[dict, str], dict] | None = None,
    ) -> None:
        self.config = config
        self.docs = docs or []
        self.auto_approve = auto_approve

        self.guard, self.tools, self.approval = build_guardrails(
            config.guardrails,
            source,
            output,
        )
        self.state = MigrationState(
            source,
            output,
            audit_dir_name=config.workspace.audit_dir_name,
        )
        self.workspace = AuditWorkspace(self.state)
        self.budget = Budget(
            max_plan_items=config.workspace.max_plan_items,
            max_retries_per_item=config.workspace.max_retries_per_item,
            max_total_patches=config.workspace.max_total_patches,
        )
        self.llm = llm or create_llm_client(config.llm)
        self._phase = "read"
        self._approve_all_remaining = False
        self._edit_previews: dict[str, dict] = {}
        self._read_docs: set[str] = set()
        self._read_attempts: set[str] = set()
        self._reviewer = reviewer or (
            lambda item, diff: review_edit(self.llm, item, diff)
        )
        self.profile = load_profile(config.migration.profile)
        self.retriever: HybridRetriever | None = None
        self.ctx = ToolContext(
            config=self.config,
            guard=self.guard,
            state=self.state,
            workspace=self.workspace,
            llm=self.llm,
            transform=self.profile.transform,
        )
        self.dispatcher = ToolDispatcher(self.tools, self.budget)
        register_tools(self.dispatcher, self.ctx)

    def run(self) -> MigrationState:
        try:
            self._initialize()
            self._agent_loop()
            self._directed_repair_pass()
            self._finish()
        except Exception as exc:
            try:
                self.state.transition(Phase.FAILED)
            except ValueError:
                pass
            self.state.add_audit("agentic", f"任务失败: {exc}")
            self.workspace.save_state()
            raise
        return self.state

    def _initialize(self) -> None:
        self.workspace.initialize()
        self.state.add_audit("agentic", "Agent 决策循环初始化完成")
        self.workspace.save_state()
        self.state.transition(Phase.SCAN)

        kb = KnowledgeBase(self.config.retrieval.kb_dir)
        sources = self.docs or list(self.profile.knowledge_base)
        for path in sources:
            if not Path(path).exists():
                continue
            kb.import_source(path)
        docs = kb.documents()
        if docs:
            self.retriever = kb.build_retriever(self.config.retrieval)
            self.ctx.retriever = self.retriever

    def _agent_loop(self) -> None:
        history = [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": "开始执行迁移任务，请按需调用工具，完成后返回 finish。",
            },
        ]

        consecutive_read_only = 0
        iteration = 0
        while True:
            iteration_limit = max(
                self.config.workspace.max_agent_iterations,
                len(self.ctx.files) * 3,
            )
            if iteration >= iteration_limit:
                break
            remaining = iteration_limit - iteration
            iteration += 1
            if remaining <= 3:
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"注意：剩余轮次仅 {remaining} 次，"
                            "请尽快完成关键操作并返回 finish。"
                        ),
                    }
                )

            history = self._trim_history(history)

            raw = None
            decision = None
            for attempt in range(3):
                try:
                    raw = self.llm.complete(
                        history,
                        max_tokens=4096,
                        json_mode=True,
                    )
                    decision = parse_json_object(raw)
                    break
                except LLMError as exc:
                    if attempt == 2:
                        self.state.add_audit(
                            "agentic",
                            f"模型响应解析失败: {exc}",
                            {"raw": (raw or "")[:2000]},
                        )
                        raise
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "你的上一次响应不是合法 JSON。请只返回 "
                                '{"action": "工具名或finish", "params": {}}，'
                                "不要包含其他内容。"
                            ),
                        }
                    )

            action = decision.get("action")
            params = (
                decision.get("params")
                if isinstance(decision.get("params"), dict)
                else {}
            )
            if action in ("finish", "write_report"):
                pending = self._collect_expected_unresolved_signals()
                if pending:
                    self.state.add_audit(
                        "agentic",
                        f"仍有 {len(pending)} 个信号未修复，不允许结束",
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "当前仍有未修复信号："
                                f"{json.dumps(pending, ensure_ascii=False)}。"
                                "请继续调用 propose_edit/apply_edit 修复后再结束。"
                            ),
                        }
                    )
                    self.workspace.save_state()
                    continue
                if action == "finish":
                    self.state.add_audit(
                        "agentic",
                        f"Agent 自主结束，共 {iteration} 轮",
                    )
                    return
                self.state.add_audit(
                    "agentic",
                    "报告由系统在收尾统一生成，Agent 提前结束",
                )
                self.workspace.save_state()
                return

            read_only = action in READ_ONLY_ACTIONS
            if self._phase == "read" and action in EXECUTE_ACTIONS:
                self._phase = "execute"
                self.state.add_audit("agentic", "进入执行阶段")
                signals = self._collect_signals_for_files()
                if signals:
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "迁移信号清单（必须逐一处理，"
                                "resolve 或给出理由，不允许漏过）：\n"
                                f"{json.dumps(signals, ensure_ascii=False)}"
                            ),
                        }
                    )
            consecutive_read_only = (
                consecutive_read_only + 1 if read_only else 0
            )
            if (
                self._phase == "execute"
                and consecutive_read_only >= 5
                and self._all_scanned_files_written()
            ):
                self.state.add_audit(
                    "agentic",
                    "连续只读操作过多，Agent 自动结束",
                )
                self.workspace.save_state()
                return

            if action == "read_document":
                doc_path = params.get("path", "")
                if not doc_path:
                    self.state.add_audit(
                        "agentic",
                        "read_document 缺少 path 参数",
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": "read_document 需要 path 参数，请补充。",
                        }
                    )
                    self.workspace.save_state()
                    continue
                if doc_path in self._read_attempts:
                    self.state.add_audit(
                        "agentic",
                        f"文档路径已尝试过，跳过: {doc_path}",
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                f"路径 {doc_path} 已尝试过（成功或失败），"
                                "请勿重复尝试。"
                            ),
                        }
                    )
                    self.workspace.save_state()
                    continue
                self._read_attempts.add(doc_path)

            if action == "apply_patch":
                patch_item = (
                    params.get("item")
                    if isinstance(params.get("item"), dict)
                    else {}
                )
                impact = patch_item.get("impact")
                if (
                    impact in self.config.guardrails.require_approval_impact
                    and not self.auto_approve
                    and not self._approve_all_remaining
                    and not self._default_confirm(patch_item)
                ):
                    self.state.add_audit(
                        "agentic",
                        f"用户拒绝应用: {patch_item.get('file')}",
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                f"用户拒绝了对 {patch_item.get('file')} 的应用，"
                                "请调整或跳过。"
                            ),
                        }
                    )
                    self.workspace.save_state()
                    continue

            if action == "apply_edit":
                edit_item = (
                    params.get("item")
                    if isinstance(params.get("item"), dict)
                    else {}
                )
                preview = self._edit_previews.get(edit_item.get("file"))
                if preview is None:
                    preview_result = self.dispatcher.call(
                        "propose_edit",
                        item=edit_item,
                    )
                    if preview_result.success:
                        preview = preview_result.result
                        self._edit_previews[edit_item.get("file")] = preview
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    "已自动生成预览: "
                                    f"{json.dumps(preview, ensure_ascii=False)[:500]}"
                                ),
                            }
                        )
                    else:
                        self.state.add_audit(
                            "agentic",
                            f"apply_edit 自动预览失败: {edit_item.get('file')}",
                            {"error": preview_result.error},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    f"无法自动生成预览: {preview_result.error}，"
                                    "请先调用 propose_edit 并修正编辑条目。"
                                ),
                            }
                        )
                        self.workspace.save_state()
                        continue

                review = self._reviewer(edit_item, preview.get("diff", ""))
                if not review.get("approved"):
                    if review.get("unavailable"):
                        self.state.add_audit(
                            "agentic",
                            f"评审不可用，记录风险后放行: {edit_item.get('file')}",
                            {"issues": review.get("issues", [])},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    f"评审不可用，已记录风险后放行: "
                                    f"{edit_item.get('file')}"
                                ),
                            }
                        )
                    else:
                        self.state.add_audit(
                            "agentic",
                            f"评审未通过: {edit_item.get('file')}",
                            {"issues": review.get("issues", [])},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    f"评审未通过: {review.get('issues')}，"
                                    "请调整编辑或跳过。"
                                ),
                            }
                        )
                        self.workspace.save_state()
                        continue

                impact = edit_item.get("impact")
                if (
                    impact in self.config.guardrails.require_approval_impact
                    and not self.auto_approve
                    and not self._approve_all_remaining
                    and not self._default_confirm(edit_item)
                ):
                    self.state.add_audit(
                        "agentic",
                        f"用户拒绝编辑: {edit_item.get('file')}",
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                f"用户拒绝了对 {edit_item.get('file')} 的编辑，"
                                "请调整或跳过。"
                            ),
                        }
                    )
                    self.workspace.save_state()
                    continue

            if action not in self.dispatcher.available():
                raise GuardrailError(f"模型调用了未注册工具: {action}")

            result = self.dispatcher.call(action, **params)
            self.state.add_audit(
                "agentic",
                f"调用工具 {action}",
                {
                    "params": params,
                    "success": result.success,
                    "error": result.error,
                },
            )
            if result.success:
                if action == "read_document":
                    doc_path = params.get("path")
                    if doc_path:
                        self._read_docs.add(doc_path)
                if action == "propose_edit":
                    preview = result.result
                    if isinstance(preview, dict) and preview.get("file"):
                        self._edit_previews[preview["file"]] = preview
                if action in ("apply_patch", "apply_edit"):
                    verified = self._auto_verify_apply(
                        action,
                        params,
                        result.result,
                    )
                    if verified:
                        self._record_applied_item(action, params, result.result)
                    else:
                        self._record_failed_item(action, params, result.result)
                if action == "apply_edit":
                    remaining_signals = self._signals_after_edit(
                        edit_item,
                        result.result,
                    )
                    if remaining_signals:
                        self.state.add_audit(
                            "agentic",
                            f"编辑后信号仍存在: {edit_item.get('file')}",
                            {"signals": remaining_signals},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    "编辑已应用但信号仍存在："
                                    f"{json.dumps(remaining_signals, ensure_ascii=False)}。"
                                    "请继续修复，移除旧写法（如 __del__），"
                                    "不能只叠加新写法。"
                                ),
                            }
                        )
                history.append({"role": "assistant", "content": raw})
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"工具 {action} 返回: "
                            f"{json.dumps(result.result, ensure_ascii=False)[:600]}"
                        ),
                    }
                )
            else:
                repair_hint = ""
                if action in ("propose_edit", "apply_edit") and (
                    "new_content" in (result.error or "")
                    or "replacement" in (result.error or "")
                ):
                    repair_hint = (
                        "编辑条目必须包含 new_content（或 replacement）字段，"
                        "即改后的完整代码；建议同时包含 start_line/end_line。"
                        '示例：{"file": "a.py", "start_line": 1, '
                        '"end_line": 2, "new_content": "...", '
                        '"evidence": {"doc_id": "d1"}, "impact": "low"}。'
                    )
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"工具 {action} 调用失败: {result.error}。"
                            f"{repair_hint}"
                            "请修正后重试。"
                        ),
                    }
                )
            self.workspace.save_state()

        self.state.add_audit(
            "agentic",
            f"达到最大迭代次数 {iteration_limit}，强制收尾",
        )
        self.workspace.save_state()

    def _directed_repair_pass(self) -> None:
        """主循环结束后，对未解析信号逐个定向修复，独立轮次预算。"""
        pending = self._sort_signals(
            self._collect_expected_unresolved_signals()
        )
        if not pending:
            return
        self.state.add_audit(
            "agentic",
            f"定向修复开始，待处理信号 {len(pending)} 个",
            {"signals": pending},
        )
        attempts_left = {
            self._signal_key(signal): DIRECTED_REPAIR_ATTEMPTS_PER_SIGNAL
            for signal in pending
        }
        max_turns = max(
            3,
            min(
                len(pending) * DIRECTED_REPAIR_ATTEMPTS_PER_SIGNAL,
                MAX_DIRECTED_REPAIR_TURNS,
            ),
        )
        for _ in range(max_turns):
            if not pending:
                break
            signal = pending[0]
            key = self._signal_key(signal)
            attempts_left[key] -= 1
            pending_files = {item["file"] for item in pending}
            self._repair_signal(signal, pending_files, attempts_left[key])
            self.workspace.save_state()

            fresh = self._sort_signals(
                self._collect_expected_unresolved_signals()
            )
            fresh_keys = {self._signal_key(item) for item in fresh}
            attempts_left = {
                item_key: attempts_left.get(
                    item_key,
                    DIRECTED_REPAIR_ATTEMPTS_PER_SIGNAL,
                )
                for item_key in fresh_keys
            }
            pending = fresh
            if key in fresh_keys and attempts_left[key] <= 0:
                self.state.add_audit(
                    "agentic",
                    f"定向修复失败，放弃信号: "
                    f"{json.dumps(signal, ensure_ascii=False)}",
                )
                pending = [
                    item for item in pending if self._signal_key(item) != key
                ]
        if pending:
            self.state.add_audit(
                "agentic",
                f"定向修复结束，仍有 {len(pending)} 个信号未修复",
                {"signals": pending},
            )
        else:
            self.state.add_audit("agentic", "定向修复结束，信号已全部消除")
        self.workspace.save_state()

    @staticmethod
    def _signal_key(signal: dict) -> tuple[str, int, str]:
        return (
            str(signal.get("file", "")),
            int(signal.get("line") or 0),
            str(signal.get("kind", "")),
        )

    @staticmethod
    def _sort_signals(signals: list[dict]) -> list[dict]:
        return sorted(
            signals,
            key=lambda signal: (
                str(signal.get("file", "")),
                int(signal.get("line") or 0),
                str(signal.get("kind", "")),
            ),
        )

    def _repair_signal(
        self,
        signal: dict,
        pending_files: set[str],
        attempts_left: int,
    ) -> bool:
        """针对单个信号生成定向编辑并应用，返回是否成功落地。"""
        snippet = self._signal_source_snippet(signal)
        if snippet is None:
            self.state.add_audit(
                "agentic",
                f"定向修复无法读取源码: {signal.get('file')}",
            )
            return False
        prompt = (
            "你现在必须定向修复一个遗留迁移信号。\n"
            "要求：\n"
            "1. 只能修改待修复文件之一，不得引入无关改动；\n"
            "2. 必须移除信号对应的旧写法，不能只叠加新写法；\n"
            "3. 返回 JSON：{\"item\": {编辑条目}}，不要返回其他内容。\n"
            "编辑条目字段：file, start_line, end_line, new_content, "
            "evidence（对象）, impact（low/medium/high，默认 low）；\n"
            "new_content 是修改后的完整代码片段，缺省行范围时视为整文件替换。\n"
            f"待修复文件: {json.dumps(sorted(pending_files), ensure_ascii=False)}\n"
            f"本次信号: {json.dumps(signal, ensure_ascii=False)}\n"
            f"当前代码片段:\n{snippet}\n"
        )
        item = None
        for _ in range(2):
            try:
                raw = self.llm.complete(
                    [
                        {"role": "system", "content": self._system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=2048,
                    json_mode=True,
                )
                data = parse_json_object(raw)
            except LLMError as exc:
                self.state.add_audit(
                    "agentic",
                    f"定向修复响应解析失败: {signal.get('file')}: {exc}",
                )
                continue
            candidate = None
            if isinstance(data, dict):
                candidate = data.get("item")
                if not isinstance(candidate, dict):
                    params = data.get("params")
                    if isinstance(params, dict):
                        candidate = params.get("item")
            if isinstance(candidate, dict):
                item = candidate
                break
            self.state.add_audit(
                "agentic",
                f"定向修复响应缺少 item: {signal.get('file')}",
                {"raw": (raw or "")[:500]},
            )
        if item is None:
            return False
        return self._apply_directed_edit(item, pending_files, signal, attempts_left)

    def _signal_source_snippet(self, signal: dict) -> str | None:
        """读取信号所在文件（优先输出副本）并返回信号行附近的代码。"""
        file = signal.get("file", "")
        line = int(signal.get("line") or 1)
        output_path = self.guard.resolve_output(file)
        if output_path.is_file():
            text = output_path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        else:
            source_path = self.guard.resolve_source(file)
            if not source_path.is_file():
                return None
            text = source_path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        lines = text.splitlines()
        start = max(1, line - 5)
        end = min(len(lines), line + 5)
        return "\n".join(
            f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1)
        )

    def _apply_directed_edit(
        self,
        item: dict,
        pending_files: set[str],
        signal: dict,
        attempts_left: int,
    ) -> bool:
        """走与主循环一致的编辑管线：预览、评审、审批、应用、验证。"""
        file = item.get("file", "")
        if file not in pending_files:
            self.state.add_audit(
                "agentic",
                f"定向编辑目标不在待修复清单内，拒绝: {file}",
            )
            return False

        normalized = dict(item)
        if (
            not isinstance(normalized.get("evidence"), dict)
            or not normalized.get("evidence")
        ):
            normalized["evidence"] = {
                "kind": signal.get("kind"),
                "line": signal.get("line"),
                "message": signal.get("message"),
            }
        if normalized.get("impact") not in VALID_IMPACT_LEVELS:
            normalized["impact"] = "low"

        preview_result = self.dispatcher.call("propose_edit", item=normalized)
        if not preview_result.success:
            self.state.add_audit(
                "agentic",
                f"定向修复预览失败: {file}: {preview_result.error}",
            )
            return False
        preview = preview_result.result
        if not isinstance(preview, dict):
            self.state.add_audit("agentic", f"定向修复预览格式异常: {file}")
            return False

        review = self._reviewer(normalized, preview.get("diff", ""))
        if not review.get("approved"):
            if review.get("unavailable"):
                self.state.add_audit(
                    "agentic",
                    f"定向修复评审不可用，记录风险后放行: {file}",
                    {"issues": review.get("issues", [])},
                )
            else:
                self.state.add_audit(
                    "agentic",
                    f"定向修复评审未通过: {file}",
                    {"issues": review.get("issues", [])},
                )
                return False

        impact = normalized.get("impact")
        if (
            impact in self.config.guardrails.require_approval_impact
            and not self.auto_approve
            and not self._approve_all_remaining
            and not self._default_confirm(normalized)
        ):
            self.state.add_audit(
                "agentic",
                f"用户拒绝定向修复: {file}",
            )
            return False

        result = self.dispatcher.call("apply_edit", item=normalized)
        self.state.add_audit(
            "agentic",
            f"定向修复调用 apply_edit: {file}",
            {
                "success": result.success,
                "error": result.error,
            },
        )
        if not result.success:
            return False
        if self._auto_verify_apply("apply_edit", {"item": normalized}, result.result):
            self._record_applied_item("apply_edit", {"item": normalized}, result.result)
            self.state.add_audit(
                "agentic",
                f"定向修复已应用: {file}（剩余尝试 {attempts_left} 次）",
            )
            return True
        self._record_failed_item("apply_edit", {"item": normalized}, result.result)
        return False

    def _finish(self) -> None:
        self.state.transition(Phase.RETRIEVE)
        self.state.transition(Phase.PLAN)
        self.state.transition(Phase.APPLY)
        self.state.transition(Phase.VERIFY)
        self._finalize_missing_files()
        self._collect_unresolved_signals()
        self.state.transition(Phase.REPORT)
        report = generate_report(self.state, self.workspace)
        self.state.add_audit("agentic", f"报告已生成: {report.name}")
        self.workspace.save_state()
        self.state.transition(Phase.DONE)
        self.workspace.save_state()

    def _finalize_missing_files(self) -> None:
        """把扫描清单中未写入输出目录的文件按原样补齐，保证项目完整。"""
        for file in self.ctx.files:
            relative = file.relative_path
            output_path = self.guard.resolve_output(relative)
            if output_path.is_file():
                continue
            item = PlanItem(
                id=f"final-{relative}",
                file=relative,
                issue="未处理文件补齐为原样复制",
                action="copy",
                impact="low",
            )
            result = apply_plan_item(item, self.guard)
            if result.success:
                self.state.add_plan_item(
                    PlanItem(
                        id=f"final-{relative}",
                        file=relative,
                        issue="未处理文件补齐为原样复制",
                        action="copy",
                        impact="low",
                        status="applied",
                        output_file=relative,
                    )
                )
                self.state.add_audit(
                    "agentic",
                    f"补齐未处理文件: {relative}",
                )
            else:
                self.state.add_audit(
                    "agentic",
                    f"补齐失败: {relative}",
                    {"error": result.error},
                )

    def _collect_unresolved_signals(self) -> None:
        """扫描输出文件，收集仍未修复的迁移信号并写入报告。"""
        signals: list[dict] = []
        for file in self.ctx.files:
            if not file.relative_path.endswith(".py"):
                continue
            output_path = self.guard.resolve_output(file.relative_path)
            if not output_path.is_file():
                continue
            text = output_path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
            signals.extend(scan_python_signals(text, file.relative_path))
        self.state.unresolved_signals = signals
        if signals:
            self.state.add_audit(
                "agentic",
                f"未修复信号 {len(signals)} 个",
                {"signals": signals},
            )

    def _collect_signals_for_files(self) -> list[dict]:
        """扫描输入项目文件，汇总当前迁移信号。"""
        signals: list[dict] = []
        for file in self.ctx.files:
            if not file.relative_path.endswith(".py"):
                continue
            source_path = self.guard.resolve_source(file.relative_path)
            if not source_path.is_file():
                continue
            text = source_path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
            signals.extend(scan_python_signals(text, file.relative_path))
        return signals

    def _collect_expected_unresolved_signals(self) -> list[dict]:
        """估算收尾后仍会存在的信号：已写文件扫输出，未写文件扫源文件。"""
        signals: list[dict] = []
        for file in self.ctx.files:
            if not file.relative_path.endswith(".py"):
                continue
            output_path = self.guard.resolve_output(file.relative_path)
            if output_path.is_file():
                text = output_path.read_text(
                    encoding="utf-8-sig",
                    errors="ignore",
                )
            else:
                source_path = self.guard.resolve_source(file.relative_path)
                text = source_path.read_text(
                    encoding="utf-8-sig",
                    errors="ignore",
                )
            signals.extend(scan_python_signals(text, file.relative_path))
        return signals

    def _signals_after_edit(self, edit_item: dict, payload: Any) -> list[dict]:
        """复验编辑后的输出文件是否仍存在迁移信号。"""
        if not isinstance(payload, dict) or not payload.get("output_path"):
            return []
        output_path = Path(payload["output_path"])
        if not output_path.is_file():
            return []
        text = output_path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )
        return scan_python_signals(text, edit_item.get("file", ""))

    def _record_applied_item(
        self,
        action: str,
        params: dict,
        payload: Any,
    ) -> None:
        item_raw = (
            params.get("item")
            if isinstance(params.get("item"), dict)
            else {}
        )
        file = item_raw.get("file", "")
        if not file:
            return
        evidence = item_raw.get("evidence", {})
        if isinstance(evidence, str):
            evidence = {"note": evidence}
        if not isinstance(evidence, dict):
            evidence = {}

        if action == "apply_patch":
            plan_item = PlanItem(
                id=item_raw.get("id") or f"applied-{file}",
                file=file,
                issue=item_raw.get("issue", "应用计划"),
                action=item_raw.get("action", "copy"),
                impact=item_raw.get("impact", "low"),
                evidence=evidence,
                status="applied",
                output_file=self._relative_output(payload),
            )
        else:
            plan_item = PlanItem(
                id=f"edit-{file.replace('/', '-')}",
                file=file,
                issue=item_raw.get("issue", "语义编辑"),
                action="edit",
                impact=item_raw.get("impact", "low"),
                evidence=evidence,
                status="applied",
                output_file=self._relative_output(payload),
            )
        self.state.add_plan_item(plan_item)

    def _auto_verify_apply(
        self,
        action: str,
        params: dict,
        payload: Any,
    ) -> bool:
        """应用后自动验证输出文件，失败则回滚。"""
        if not isinstance(payload, dict) or not payload.get("output_path"):
            return False
        output_path = Path(payload["output_path"])
        verify = self.dispatcher.call("run_verifier", path=str(output_path))
        if verify.success and verify.result.get("success"):
            return True
        output_path.unlink(missing_ok=True)
        file = params.get("item", {}).get("file", "") if isinstance(
            params.get("item"), dict
        ) else ""
        self.state.add_audit(
            "agentic",
            f"应用后验证失败，已回滚: {file}",
            {"verify_error": verify.error or "验证失败"},
        )
        return False

    def _record_failed_item(
        self,
        action: str,
        params: dict,
        payload: Any,
    ) -> None:
        item_raw = (
            params.get("item")
            if isinstance(params.get("item"), dict)
            else {}
        )
        file = item_raw.get("file", "")
        if not file:
            return
        evidence = item_raw.get("evidence", {})
        if isinstance(evidence, str):
            evidence = {"note": evidence}
        plan_item = PlanItem(
            id=item_raw.get("id") or f"applied-{file}",
            file=file,
            issue=item_raw.get("issue", "应用计划"),
            action=(
                "edit"
                if action == "apply_edit"
                else item_raw.get("action", "copy")
            ),
            impact=item_raw.get("impact", "low"),
            evidence=evidence if isinstance(evidence, dict) else {},
            status="failed",
            error="应用后验证失败，已回滚",
            output_file=self._relative_output(payload),
        )
        self.state.add_plan_item(plan_item)

    def _relative_output(self, payload: Any) -> str | None:
        if not isinstance(payload, dict) or not payload.get("output_path"):
            return None
        output_path = Path(payload["output_path"])
        try:
            return output_path.relative_to(self.state.output_root).as_posix()
        except ValueError:
            return str(output_path)

    def _system_prompt(self) -> str:
        index = build_document_index()
        red_lines = build_red_lines()
        tools = json.dumps(TOOL_DESCRIPTIONS, ensure_ascii=False)
        iteration_cap = max(
            self.config.workspace.max_agent_iterations,
            DEFAULT_MAX_AGENT_ITERATIONS,
        )
        return (
            "你是企业级代码库迁移 Agent。当前任务：\n"
            f"迁移档案: {self.profile.name}（{self.config.migration.scope}）\n"
            f"输入项目: {self.state.source_root}\n"
            f"输出目录: {self.state.output_root}\n"
            "可用工具：\n"
            f"{tools}\n"
            "每次只能返回一个 JSON："
            '{"thought": "说明", "action": "工具名或finish", "params": {}}。\n'
            "不得调用白名单之外的任何命令。\n"
            f"{index}\n\n"
            f"{red_lines}\n"
            "需要规则或技能细节时，调用 read_document(path) 按需读取，"
            "不要一次性读取全部文档。\n"
            f"轮次约束：最多执行 {iteration_cap} 轮（按文件数动态放大），"
            "完成任务后立即返回 finish；\n"
            "同一文档只读取一次，不要重复读取；\n"
            "轮次接近上限时会收到提醒，请尽快收尾；\n"
            "语义问题（内存泄漏/并发/废弃 API）必须使用 propose_edit 与 "
            "apply_edit，apply_patch 只用于固定语法规则；\n"
            "write_report 生成报告后任务即完成，应结束循环；\n"
            "先读取必要文档与源码，读取阶段不会被打断；"
            "开始执行（propose_plan/编辑/应用/验证）后进入执行阶段；\n"
            "进入执行阶段后 harness 会提供迁移信号清单，"
            "必须逐一 resolve 或给出理由；\n"
            "编辑必须移除信号对应的旧写法，不能只叠加新写法；"
            "编辑后 harness 会复验信号是否消除。"
        )

    def _trim_history(self, messages: list[dict]) -> list[dict]:
        """裁剪历史：保留 system、最新消息，并插入运行摘要。"""
        if len(messages) <= MAX_HISTORY_MESSAGES:
            return messages
        head = [messages[0]]
        summary = {
            "role": "user",
            "content": f"（历史已裁剪）当前运行摘要：{self._state_summary()}",
        }
        tail = messages[-(MAX_HISTORY_MESSAGES - 2):]
        return head + [summary] + tail

    def _state_summary(self) -> str:
        counts = self.dispatcher.call_counts()
        return (
            f"已调用工具 {sum(counts.values())} 次；"
            f"已应用补丁 {counts.get('apply_patch', 0)} 次；"
            f"已读取文档 {len(self._read_docs)} 份；"
            f"报告已生成 {counts.get('write_report', 0) > 0}"
        )

    def _all_scanned_files_written(self) -> bool:
        if not self.ctx.files:
            return False
        return all(
            self.guard.resolve_output(file.relative_path).is_file()
            for file in self.ctx.files
        )

    def _default_confirm(self, item: dict) -> bool:
        if self._approve_all_remaining:
            return True
        answer = input(
            f"是否应用编辑 {item.get('file')}？"
            f"（y 同意 / n 跳过 / a 全部同意）[y/N/a]: "
        ).strip().lower()
        if answer in {"a", "all", "全部"}:
            self._approve_all_remaining = True
            return True
        return answer in {"y", "yes"}
