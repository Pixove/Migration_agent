from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from agent.config import VALID_IMPACT_LEVELS, AppConfig
from agent.context_loader import PROJECT_ROOT
from agent.dispatcher import ToolDispatcher, ToolSpec
from agent.guardrails import Budget, PathGuard, ToolRegistry
from agent.llm import LLMClient, LLMError
from agent.planning import build_fallback_plan, generate_llm_plan
from agent.state import AuditWorkspace, MigrationState, PlanItem
from retrieval import HybridRetriever
from retrieval.documents import RetrievalError
from tools.patcher import apply_edit_item, apply_line_edit, apply_plan_item
from tools.reporter import write_report
from tools.scanner import FileInfo, scan_project
from tools.verifier import verify_file

ALLOWED_DOC_PREFIXES = ("rules/", "skills/")


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
    transform: Callable[[str, Any], str] | None = None


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
    if item.action == "transform" and not item.evidence:
        return {
            "success": False,
            "output_path": None,
            "diff": "",
            "error": "transform 计划缺少证据",
        }
    transform = ctx.transform if item.action == "transform" else None
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


def _read_document(
    ctx: ToolContext,
    path: str = "",
    max_chars: int = 8000,
    **kwargs: Any,
) -> dict[str, Any]:
    """按需读取规则/技能/文档，限制在允许目录内。"""
    if not path:
        raise ValueError("read_document 需要 path 参数")
    raw = Path(path)
    if raw.is_absolute():
        raise ValueError("read_document 只接受相对路径")
    normalized = raw.as_posix()
    if not normalized.startswith(ALLOWED_DOC_PREFIXES):
        raise ValueError(f"只能读取规则/技能/文档目录: {path}")
    if ".." in raw.parts:
        raise ValueError(f"路径越界: {path}")

    target = (PROJECT_ROOT / raw).resolve()
    root = PROJECT_ROOT.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径越界: {path}") from exc
    if not target.is_file():
        raise ValueError(f"文档不存在: {path}")

    content = target.read_text(encoding="utf-8")
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return {"path": normalized, "content": content, "truncated": truncated}


def _validate_edit_item(item: Any) -> dict:
    if not isinstance(item, dict):
        raise ValueError("编辑条目必须是对象")
    file = str(item.get("file", ""))
    if not file:
        raise ValueError("编辑条目缺少 file")
    start = item.get("start_line")
    end = item.get("end_line")
    content = item.get("new_content")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("start_line/end_line 必须是整数")
    if start < 1 or end < start:
        raise ValueError(f"无效行范围: {start}-{end}")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("编辑条目缺少 new_content")
    evidence = item.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("编辑必须携带证据")
    impact = str(item.get("impact", ""))
    if impact not in VALID_IMPACT_LEVELS:
        raise ValueError(f"非法影响面: {impact}")
    return item


def _propose_edit(ctx: ToolContext, item: Any = None, **kwargs: Any) -> dict[str, Any]:
    """生成语义编辑 diff 预览，不写任何文件。"""
    item = _validate_edit_item(item)
    source_path = ctx.guard.resolve_source(item["file"])
    source_text = source_path.read_text(encoding="utf-8-sig", errors="ignore")
    new_text = apply_line_edit(
        source_text,
        item["start_line"],
        item["end_line"],
        item["new_content"],
    )
    diff = "".join(
        difflib.unified_diff(
            source_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{item['file']}",
            tofile=f"b/{item['file']}",
        )
    )
    return {"file": item["file"], "diff": diff, "preview": new_text}


def _apply_edit(ctx: ToolContext, item: Any = None, **kwargs: Any) -> dict[str, Any]:
    """应用一条语义编辑到输出目录。"""
    item = _validate_edit_item(item)
    result = apply_edit_item(item, ctx.guard)
    return {
        "success": result.success,
        "output_path": (
            str(result.output_path) if result.output_path else None
        ),
        "diff": result.diff,
        "error": result.error,
    }


def register_tools(dispatcher: ToolDispatcher, ctx: ToolContext) -> None:
    """注册六个白名单工具，将工具名映射到实现函数。"""
    specs = [
        ToolSpec("scan_files", "扫描输入项目，返回文件清单", _scan_files, max_calls=1),
        ToolSpec("retrieve_examples", "从知识库检索迁移范例", _retrieve_examples, max_calls=20),
        ToolSpec("propose_plan", "生成并校验迁移计划", _propose_plan, max_calls=3),
        ToolSpec("apply_patch", "在输出目录应用计划条目", _apply_patch, max_calls=500),
        ToolSpec("run_verifier", "验证输出文件", _run_verifier, max_calls=500),
        ToolSpec("write_report", "生成中文迁移报告", _write_report, max_calls=1),
        ToolSpec("read_document", "按需读取规则/技能/文档", _read_document, max_calls=10),
        ToolSpec("propose_edit", "生成语义编辑 diff 预览（不写文件）", _propose_edit, max_calls=20),
        ToolSpec("apply_edit", "应用语义编辑到输出目录", _apply_edit, max_calls=100),
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
