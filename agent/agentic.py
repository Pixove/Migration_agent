from __future__ import annotations

import json
from pathlib import Path

from agent.config import AppConfig
from agent.context_loader import build_document_index, build_red_lines
from agent.dispatcher import ToolDispatcher
from agent.guardrails import Budget, GuardrailError, build_guardrails
from agent.llm import (
    LLMClient,
    LLMError,
    create_llm_client,
    parse_json_object,
)
from agent.state import AuditWorkspace, MigrationState, Phase
from agent.tooling import ToolContext, register_tools
from migration.registry import load_profile
from retrieval import HybridRetriever
from retrieval.knowledge_base import KnowledgeBase

MAX_AGENT_ITERATIONS = 20

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
        self.profile = load_profile(config.migration.profile)
        self.retriever: HybridRetriever | None = None
        self.ctx = ToolContext(
            config=self.config,
            guard=self.guard,
            state=self.state,
            workspace=self.workspace,
            llm=None,
            transform=self.profile.transform,
        )
        self.dispatcher = ToolDispatcher(self.tools, self.budget)
        register_tools(self.dispatcher, self.ctx)

    def run(self) -> MigrationState:
        try:
            self._initialize()
            self._agent_loop()
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
        sources = self.docs or [self.profile.knowledge_base]
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

        for iteration in range(MAX_AGENT_ITERATIONS):
            try:
                raw = self.llm.complete(history, max_tokens=2048)
                decision = parse_json_object(raw)
            except LLMError as exc:
                self.state.add_audit("agentic", f"模型响应解析失败: {exc}")
                raise

            action = decision.get("action")
            params = (
                decision.get("params")
                if isinstance(decision.get("params"), dict)
                else {}
            )
            if action == "finish":
                self.state.add_audit(
                    "agentic",
                    f"Agent 自主结束，共 {iteration + 1} 轮",
                )
                return

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
                history.append({"role": "assistant", "content": raw})
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"工具 {action} 返回: "
                            f"{json.dumps(result.result, ensure_ascii=False)[:2000]}"
                        ),
                    }
                )
            else:
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"工具 {action} 调用失败: {result.error}，"
                            "请换一种方式继续。"
                        ),
                    }
                )
            self.workspace.save_state()

        raise RuntimeError(f"Agent 超过最大迭代次数 {MAX_AGENT_ITERATIONS}")

    def _finish(self) -> None:
        self.state.transition(Phase.RETRIEVE)
        self.state.transition(Phase.PLAN)
        self.state.transition(Phase.APPLY)
        self.state.transition(Phase.VERIFY)
        self.state.transition(Phase.REPORT)
        if self.dispatcher.call_counts().get("write_report", 0) == 0:
            result = self.dispatcher.call("write_report")
            if not result.success:
                raise RuntimeError(f"write_report 失败: {result.error}")
        self.state.add_audit("agentic", "报告生成完成")
        self.workspace.save_state()
        self.state.transition(Phase.DONE)
        self.workspace.save_state()

    def _system_prompt(self) -> str:
        index = build_document_index()
        red_lines = build_red_lines()
        tools = json.dumps(TOOL_DESCRIPTIONS, ensure_ascii=False)
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
            "不要一次性读取全部文档。"
        )
