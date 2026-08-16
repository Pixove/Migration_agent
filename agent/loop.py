from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agent.config import AppConfig
from agent.guardrails import Budget, build_guardrails
from agent.llm import LLMError, create_llm_client
from agent.planning import build_fallback_plan, generate_llm_plan
from agent.state import AuditWorkspace, MigrationState, Phase, PlanItem
from retrieval import HybridRetriever
from retrieval.documents import Document, load_documents
from tools.patcher import apply_plan_item
from tools.reporter import write_report
from tools.scanner import FileInfo, scan_project
from tools.verifier import verify_file


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
    ) -> None:
        self.config = config
        self.docs = docs or []
        self.auto_approve = auto_approve
        self._confirm = confirm or self._default_confirm

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
        files = scan_project(
            self.state.source_root,
            self.config.guardrails,
            self.guard,
        )
        self.state.add_audit(
            "scan_files",
            f"扫描完成，发现 {len(files)} 个文件",
            {"file_count": len(files)},
        )
        self.workspace.save_state()
        return files

    def _retrieve(self) -> None:
        self.state.transition(Phase.RETRIEVE)
        docs: list[Document] = []
        for path in self.docs:
            docs.extend(load_documents(path))
        self.state.add_audit(
            "retrieve_examples",
            f"导入文档 {len(docs)} 篇",
            {"doc_count": len(docs)},
        )
        if docs:
            self.retriever = HybridRetriever(self.config.retrieval)
            self.retriever.index(docs)
        self.workspace.save_state()

    def _plan(self, files: list[FileInfo]) -> list[PlanItem]:
        self.state.transition(Phase.PLAN)
        file_paths = sorted(file.relative_path for file in files)

        if self.llm is None:
            plan = build_fallback_plan(file_paths)
            source = "fallback"
        else:
            try:
                plan = generate_llm_plan(self.llm, file_paths)
                source = "llm"
            except LLMError as exc:
                plan = build_fallback_plan(file_paths)
                source = "fallback"
                self.state.add_audit(
                    "propose_plan",
                    f"LLM 计划失败，使用回退计划: {exc}",
                )

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
        result = apply_plan_item(item, self.guard)
        if not result.success:
            item.status = "failed"
            item.error = result.error
            self.state.add_audit(
                "apply_patch",
                f"应用失败: {item.file}",
                {"item_id": item.id, "error": result.error},
            )
            return

        item.status = "applied"
        item.output_file = result.output_path.relative_to(
            self.state.output_root
        ).as_posix()
        verification = verify_file(result.output_path)
        if not verification.success:
            item.status = "failed"
            item.error = "; ".join(
                check.message for check in verification.checks if not check.ok
            )
            result.output_path.unlink(missing_ok=True)
            item.error += "；已回滚输出文件"
        else:
            self.budget.record_patch()

        self.state.add_audit(
            "apply_patch",
            f"应用完成: {item.file}",
            {
                "item_id": item.id,
                "verified": verification.success,
                "diff_length": len(result.diff),
            },
        )

    def _finish(self) -> None:
        self.state.transition(Phase.VERIFY)
        self.state.transition(Phase.REPORT)
        report = write_report(self.state, self.workspace)
        self.state.add_audit("write_report", f"报告已生成: {report.name}")
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
