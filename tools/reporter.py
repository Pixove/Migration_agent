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
    ]
    if state.profile:
        scope = f"（{state.scope}）" if state.scope else ""
        lines.insert(5, f"- 迁移档案: `{state.profile}`{scope}")
    lines.extend(["## 迁移计划", ""])

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
            rule_id = _evidence_value(item.evidence, "rule_id")
            api = _evidence_value(item.evidence, "api")
            docs = _evidence_value(item.evidence, "docs")
            if rule_id:
                lines.append(f"- 规则: `{rule_id}`")
            if api:
                lines.append(f"- API: `{api}`")
            if docs:
                lines.append(f"- 证据文档: `{docs}`")
            if item.output_file:
                lines.append(f"- 输出文件: `{item.output_file}`")
            if item.error:
                lines.append(f"- 错误: {item.error}")
            lines.append("")

    if state.unresolved_signals:
        lines.append("## 未修复信号")
        lines.append("")
        for signal in state.unresolved_signals:
            detail = (
                f"- {signal.get('file')} 第 {signal.get('line')} 行: "
                f"{signal.get('message')}"
            )
            if signal.get("rule_id"):
                detail += f"（规则: {signal['rule_id']}）"
            if signal.get("api"):
                detail += f"（API: {signal['api']}）"
            if signal.get("docs"):
                detail += f"（文档: {signal['docs']}）"
            lines.append(detail)
        lines.append("")

    if state.verification_checks:
        lines.append("## 行为验证")
        lines.append("")
        for check in state.verification_checks:
            status = "通过" if check.get("ok") else "失败"
            message = check.get("message") or ""
            suffix = f"：{message}" if message else ""
            lines.append(
                f"- {status}: `{check.get('name')}`{suffix}"
            )
        lines.append("")

    report_path = workspace.state.audit_dir() / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _evidence_value(evidence: dict, key: str):
    """从可能嵌套的证据对象中提取指定字段。"""
    if not isinstance(evidence, dict):
        return None
    value = evidence.get(key)
    if isinstance(value, (str, int, float)):
        return value
    for child in evidence.values():
        if isinstance(child, dict):
            nested = _evidence_value(child, key)
            if nested is not None:
                return nested
    return None
