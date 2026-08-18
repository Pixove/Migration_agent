from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agent.config import AppConfig
from agent.dispatcher import ToolDispatcher
from agent.guardrails import Budget, GuardrailError, build_guardrails
from agent.llm import create_llm_client
from agent.planning import build_fallback_plan, refactor_ratio
from agent.state import AuditWorkspace, MigrationState, Phase, PlanItem
from agent.tooling import ToolContext, register_tools
from retrieval import HybridRetriever
from retrieval.knowledge_base import KnowledgeBase
from tools.scanner import FileInfo


class MigrationRunner:
    """Agent 主循环：初始化、扫描、检索、规划、应用、验证、报告。"""

    def __init__(
        self,
        config: AppConfig,
        source: str | Path,
        output: str | Path,
        *,
        docs: list[str | Path] | None = None,
        no_llm: bool = False,
        auto_approve: bool = False,
        confirm: Callable[[PlanItem], bool] | None = None,
        large_refactor_confirm: Callable[[float], bool] | None = None,
    ) -> None:
        self.config = config
        self.docs = docs or []
        self.auto_approve = auto_approve
        self._confirm = confirm or self._default_confirm
        self._large_refactor_confirm = (
            large_refactor_confirm or self._default_large_refactor_confirm
        )

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
        self.llm = None if no_llm else create_llm_client(config.llm)
        self.retriever: HybridRetriever | None = None
        self.ctx = ToolContext(
            config=self.config,
            guard=self.guard,
            state=self.state,
            workspace=self.workspace,
            llm=self.llm,
        )
        self.dispatcher = ToolDispatcher(self.tools, self.budget)
        register_tools(self.dispatcher, self.ctx)

    def run(self) -> MigrationState:
        try:
            self._initialize()
            files = self._scan()
            self._retrieve()
            plan = self._plan(files)
            self._apply()
            self._finish()
        except Exception as exc:
            try:
                self.state.transition(Phase.FAILED)
            except ValueError:
                pass
            self.state.add_audit("runner", f"任务失败: {exc}")
            self.workspace.save_state()
            raise
        return self.state

    def _initialize(self) -> None:
        self.workspace.initialize()
        self.state.add_audit("runner", "任务初始化完成")
        self.workspace.save_state()
        self.state.transition(Phase.SCAN)

    def _scan(self) -> list[FileInfo]:
        result = self.dispatcher.call("scan_files")
        if not result.success:
            raise RuntimeError(f"scan_files 失败: {result.error}")
        files = self.ctx.files
        self.state.add_audit(
            "scan_files",
            f"扫描完成，发现 {len(files)} 个文件",
            {"file_count": len(files)},
        )
        self.workspace.save_state()
        return files

    def _retrieve(self) -> None:
        self.state.transition(Phase.RETRIEVE)
        kb = KnowledgeBase(self.config.retrieval.kb_dir)
        for path in self.docs:
            stats = kb.import_source(path)
            self.state.add_audit(
                "retrieve_examples",
                f"导入知识库: {path}（新增 {stats['added']}，更新 {stats['updated']}，跳过 {stats['skipped']}）",
                {"path": str(path), **stats},
            )

        docs = kb.documents()
        self.state.add_audit(
            "retrieve_examples",
            f"知识库共 {len(docs)} 篇文档",
            {"doc_count": len(docs), "kb_dir": str(kb.root)},
        )
        if docs:
            self.retriever = kb.build_retriever(self.config.retrieval)
            self.ctx.retriever = self.retriever
        self.kb = kb
        self.workspace.save_state()

    def _plan(self, files: list[FileInfo]) -> list[PlanItem]:
        self.state.transition(Phase.PLAN)
        file_paths = sorted(file.relative_path for file in files)

        evidence, evidence_pool = self._collect_evidence(file_paths)
        result = self.dispatcher.call(
            "propose_plan",
            files=file_paths,
            evidence=evidence,
            evidence_pool=evidence_pool,
        )
        if result.success:
            payload = result.result
            plan = [PlanItem(**item) for item in payload["items"]]
            source = payload.get("source", "fallback")
            llm_error = payload.get("error")
            if llm_error:
                self.state.add_audit(
                    "propose_plan",
                    f"LLM 计划失败，使用回退计划: {llm_error}",
                )
        else:
            plan = build_fallback_plan(file_paths)
            source = "fallback"
            self.state.add_audit(
                "propose_plan",
                f"计划工具失败，使用回退计划: {result.error}",
            )

        self._enforce_refactor_threshold(plan, files)

        for item in plan:
            self.budget.record_plan_item()
            self.state.add_plan_item(item)
        self.state.add_audit(
            "propose_plan",
            f"计划生成完成，来源 {source}，共 {len(plan)} 条",
            {"source": source, "count": len(plan)},
        )
        self.workspace.save_state()
        return plan

    def _enforce_refactor_threshold(
        self,
        plan: list[PlanItem],
        files: list[FileInfo],
    ) -> float:
        """重构比例超过阈值时必须征得用户同意。"""
        file_lines = {file.relative_path: file.line_count for file in files}
        ratio = refactor_ratio(plan, file_lines)
        threshold = self.config.guardrails.max_refactor_ratio
        if ratio > threshold:
            if not self._large_refactor_confirm(ratio):
                raise GuardrailError(
                    f"重构比例 {ratio:.1%} 超过阈值 {threshold:.1%}，"
                    "未获得用户同意，任务终止"
                )
            self.state.add_audit(
                "propose_plan",
                f"大规模重构 {ratio:.1%} 已获得用户同意",
                {"ratio": ratio},
            )
        return ratio

    def _collect_evidence(
        self,
        file_paths: list[str],
    ) -> tuple[list[dict], list[str]]:
        """为每个文件检索 Top-K 范例，并汇总证据文档 ID。"""
        if self.retriever is None:
            return [], []

        evidence: list[dict] = []
        pool: set[str] = set()
        for file_path in file_paths:
            if not file_path.endswith(".py"):
                continue
            source_path = self.guard.resolve_source(file_path)
            snippet = ""
            try:
                snippet = source_path.read_text(
                    encoding="utf-8-sig",
                    errors="ignore",
                )[:100]
            except OSError:
                snippet = ""

            query = f"{file_path} {snippet}".strip()
            hits = self.retriever.search(query, top_k=2)
            evidence.append(
                {
                    "file": file_path,
                    "hits": [
                        {
                            "doc_id": hit.document.doc_id,
                            "score": hit.score,
                            "source": hit.source,
                            "snippet": hit.document.text[:100],
                        }
                        for hit in hits
                    ],
                }
            )
            pool.update(hit.document.doc_id for hit in hits)
        return evidence, sorted(pool)

    def _apply(self) -> None:
        self.state.transition(Phase.APPLY)
        for item in self.state.plan_items:
            self._apply_item(item)
            self.workspace.save_state()

    def _apply_item(self, item: PlanItem) -> None:
        if self.approval.needs_approval(item.impact) and not self.auto_approve:
            if not self._confirm(item):
                item.status = "skipped"
                self.state.add_audit(
                    "apply_patch",
                    f"人工审批跳过: {item.file}",
                    {"item_id": item.id},
                )
                return

        self.budget.check_patch()
        patch_call = self.dispatcher.call("apply_patch", item=item)
        if not patch_call.success:
            item.status = "failed"
            item.error = patch_call.error
            self.state.add_audit(
                "apply_patch",
                f"应用失败: {item.file}",
                {"item_id": item.id, "error": patch_call.error},
            )
            return

        patch = patch_call.result
        if not patch["success"]:
            item.status = "failed"
            item.error = patch["error"]
            self.state.add_audit(
                "apply_patch",
                f"应用失败: {item.file}",
                {"item_id": item.id, "error": patch["error"]},
            )
            return

        item.status = "applied"
        output_path = Path(patch["output_path"])
        item.output_file = output_path.relative_to(self.state.output_root).as_posix()

        verify_call = self.dispatcher.call("run_verifier", path=str(output_path))
        if not verify_call.success:
            item.status = "failed"
            item.error = f"验证工具调用失败: {verify_call.error}"
            output_path.unlink(missing_ok=True)
            item.error += "；已回滚输出文件"
        else:
            verification = verify_call.result
            if not verification["success"]:
                item.status = "failed"
                item.error = "; ".join(
                    check["message"]
                    for check in verification["checks"]
                    if not check["ok"]
                )
                output_path.unlink(missing_ok=True)
                item.error += "；已回滚输出文件"
            else:
                self.budget.record_patch()

        self.state.add_audit(
            "apply_patch",
            f"应用完成: {item.file}",
            {
                "item_id": item.id,
                "verified": item.status == "applied",
                "diff_length": len(patch["diff"]),
            },
        )

    def _finish(self) -> None:
        self.state.transition(Phase.VERIFY)
        self.state.transition(Phase.REPORT)
        result = self.dispatcher.call("write_report")
        if not result.success:
            raise RuntimeError(f"write_report 失败: {result.error}")
        report_name = Path(result.result["path"]).name
        self.state.add_audit("write_report", f"报告已生成: {report_name}")
        self.workspace.save_state()
        self.state.transition(Phase.DONE)
        self.workspace.save_state()

    @staticmethod
    def _default_confirm(item: PlanItem) -> bool:
        answer = input(
            f"计划 [{item.id}] 影响面为 {item.impact}，"
            f"是否应用到 {item.file}? [y/N]: "
        ).strip().lower()
        return answer in {"y", "yes"}

    @staticmethod
    def _default_large_refactor_confirm(ratio: float) -> bool:
        answer = input(
            f"重构比例 {ratio:.1%} 超过阈值，是否继续? [y/N]: "
        ).strip().lower()
        return answer in {"y", "yes"}
