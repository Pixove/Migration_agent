from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent.guardrails import PathGuard
from agent.state import PlanItem


@dataclass
class PatchResult:
    success: bool
    output_path: Path | None = None
    diff: str = ""
    error: str | None = None


def apply_plan_item(
    item: PlanItem,
    guard: PathGuard,
    transform: Callable[[str, PlanItem], str] | None = None,
) -> PatchResult:
    """在输出目录内应用一条迁移计划。

    action 为 copy 或未提供 transform 时，先按原样落盘；
    后续具体迁移逻辑通过 transform 钩子接入。
    """
    source_path = guard.resolve_source(item.file)
    output_path = guard.resolve_output(item.file)

    try:
        source_text = source_path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError as exc:
        return PatchResult(success=False, error=f"读取源文件失败: {exc}")

    new_text = source_text if transform is None else transform(source_text, item)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return PatchResult(success=False, error=f"写入输出文件失败: {exc}")

    diff = "".join(
        difflib.unified_diff(
            source_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{item.file}",
            tofile=f"b/{item.file}",
        )
    )
    return PatchResult(success=True, output_path=output_path, diff=diff)


def apply_line_edit(
    source_text: str,
    start_line: int,
    end_line: int,
    new_content: str,
) -> str:
    """按行范围替换源码片段。"""
    lines = source_text.splitlines(keepends=True)
    if start_line < 1 or end_line > len(lines) or start_line > end_line:
        raise ValueError(
            f"无效行范围: {start_line}-{end_line}，文件共 {len(lines)} 行"
        )
    if (
        new_content
        and not new_content.endswith(("\n", "\r"))
        and end_line < len(lines)
    ):
        new_content += "\n"
    return "".join(lines[: start_line - 1] + [new_content] + lines[end_line:])


def apply_edit_item(item: dict, guard: PathGuard) -> PatchResult:
    """在输出目录内应用一条语义编辑。"""
    source_path = guard.resolve_source(item["file"])
    output_path = guard.resolve_output(item["file"])
    source_text = source_path.read_text(encoding="utf-8-sig", errors="ignore")
    new_text = apply_line_edit(
        source_text,
        item["start_line"],
        item["end_line"],
        item["new_content"],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_text, encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            source_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{item['file']}",
            tofile=f"b/{item['file']}",
        )
    )
    return PatchResult(success=True, output_path=output_path, diff=diff)
