from __future__ import annotations

from pathlib import Path

from agent.state import AuditWorkspace, MigrationState


def write_report(state: MigrationState, workspace: AuditWorkspace) -> Path:
    """在审计目录生成中文迁移报告。"""
    lines = [
        "# 迁移报告",
        "",
        f"- 输入项目: `{state.source_root}`",
        f"- 输出目录: `{state.output_root}`",
        f"- 当前阶段: `{state.phase.value}`",
        f"- 计划条目: {len(state.plan_items)}",
        f"- 审计记录: {len(state.audit_entries)}",
        "",
        "## 迁移计划",
        "",
    ]

    if not state.plan_items:
        lines.append("暂无计划条目。")
    else:
        for item in state.plan_items:
            lines.append(f"### {item.file}")
            lines.append(f"- 编号: {item.id}")
            lines.append(f"- 问题: {item.issue}")
            lines.append(f"- 动作: {item.action}")
            lines.append(f"- 影响面: {item.impact}")
            lines.append(f"- 状态: {item.status}")
            if item.output_file:
                lines.append(f"- 输出文件: `{item.output_file}`")
            if item.error:
                lines.append(f"- 错误: {item.error}")
            lines.append("")

    report_path = workspace.state.audit_dir() / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
