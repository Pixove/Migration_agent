from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import partial
from typing import Any

from agent.config import AppConfig
from agent.dispatcher import ToolDispatcher, ToolSpec
from agent.guardrails import Budget, PathGuard, ToolRegistry
from agent.llm import LLMClient, LLMError
from agent.planning import build_fallback_plan, generate_llm_plan
from agent.state import AuditWorkspace, MigrationState, PlanItem
from migration.py2to3 import transform_python2_to_3
from retrieval import HybridRetriever
from retrieval.documents import RetrievalError
from tools.patcher import apply_plan_item
from tools.reporter import write_report
from tools.scanner import FileInfo, scan_project
from tools.verifier import verify_file


@dataclass
class ToolContext:
    """工具运行时的共享上下文。"""

    config: AppConfig
    guard: PathGuard
    files: list[FileInfo] = field(default_factory=list)
    retriever: HybridRetriever | None = None
    state: MigrationState | None = None
    workspace: AuditWorkspace | None = None
    llm: LLMClient | None = None


def _scan_files(ctx: ToolContext, **kwargs: Any) -> list[dict[str, object]]:
    files = scan_project(
        ctx.guard.source_root,
        ctx.config.guardrails,
        ctx.guard,
    )
    ctx.files = files
    return [file.to_dict() for file in files]


def _retrieve_examples(
    ctx: ToolContext,
    query: str = "",
    top_k: int = 5,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    if ctx.retriever is None:
        raise RetrievalError("知识库未加载，请先导入文档")
    hits = ctx.retriever.search(query, top_k=top_k)
    return [
        {
            "doc_id": hit.document.doc_id,
            "score": hit.score,
            "source": hit.source,
            "snippet": hit.document.text[:200],
        }
        for hit in hits
    ]


def _propose_plan(
    ctx: ToolContext,
    files: list[str] | None = None,
    evidence: list[dict] | None = None,
    evidence_pool: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    file_paths = files or [file.relative_path for file in ctx.files]
    if ctx.llm is None:
        return {
            "source": "fallback",
            "items": [asdict(item) for item in build_fallback_plan(file_paths)],
            "error": None,
        }
    try:
        plan = generate_llm_plan(
            ctx.llm,
            file_paths,
            evidence=evidence,
            evidence_pool=evidence_pool,
        )
        return {
            "source": "llm",
            "items": [asdict(item) for item in plan],
            "error": None,
            "evidence_count": len(evidence or []),
        }
    except LLMError as exc:
        return {
            "source": "fallback",
            "items": [asdict(item) for item in build_fallback_plan(file_paths)],
            "error": str(exc),
        }


def _apply_patch(ctx: ToolContext, item: Any = None, **kwargs: Any) -> dict[str, Any]:
    if item is None:
        raise ValueError("apply_patch 需要 item 参数")
    if isinstance(item, dict):
        item = PlanItem(**item)
    transform = transform_python2_to_3 if item.action == "transform" else None
    result = apply_plan_item(item, ctx.guard, transform=transform)
    return {
        "success": result.success,
        "output_path": str(result.output_path) if result.output_path else None,
        "diff": result.diff,
        "error": result.error,
    }


def _run_verifier(ctx: ToolContext, path: str | None = None, **kwargs: Any) -> dict[str, Any]:
    if not path:
        raise ValueError("run_verifier 需要 path 参数")
    result = verify_file(path)
    return {
        "success": result.success,
        "checks": [
            {"name": check.name, "ok": check.ok, "message": check.message}
            for check in result.checks
        ],
    }


def _write_report(ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
    if ctx.state is None or ctx.workspace is None:
        raise ValueError("write_report 尚未绑定任务状态")
    path = write_report(ctx.state, ctx.workspace)
    return {"path": str(path)}


def register_tools(dispatcher: ToolDispatcher, ctx: ToolContext) -> None:
    """注册六个白名单工具，将工具名映射到实现函数。"""
    specs = [
        ToolSpec("scan_files", "扫描输入项目，返回文件清单", _scan_files, max_calls=1),
        ToolSpec("retrieve_examples", "从知识库检索迁移范例", _retrieve_examples, max_calls=20),
        ToolSpec("propose_plan", "生成并校验迁移计划", _propose_plan, max_calls=3),
        ToolSpec("apply_patch", "在输出目录应用计划条目", _apply_patch, max_calls=500),
        ToolSpec("run_verifier", "验证输出文件", _run_verifier, max_calls=500),
        ToolSpec("write_report", "生成中文迁移报告", _write_report, max_calls=1),
    ]
    for spec in specs:
        dispatcher.register(
            ToolSpec(
                name=spec.name,
                description=spec.description,
                fn=partial(spec.fn, ctx),
                max_calls=spec.max_calls,
            )
        )
