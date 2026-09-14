from __future__ import annotations

from pathlib import Path

from agent.config import AppConfig, load_config
from migration.registry import load_profile
from migration.scan_signals import (
    rules_paths_for_profile,
    scan_python_signals,
)
from tools.verifier import run_behavior_verification, verify_file


def run_quality_evals(
    output_root: str | Path,
    config: AppConfig | None = None,
) -> dict:
    """评估已迁移输出目录的语法、信号清除和行为验证结果。"""
    config = config or load_config("config.yaml")
    root = Path(output_root)
    if not root.is_dir():
        return {
            "error": f"输出目录不存在: {root}",
            "overall_success": False,
        }

    audit_dir_name = config.workspace.audit_dir_name
    py_files = [
        path
        for path in sorted(root.rglob("*.py"))
        if path.is_file() and audit_dir_name not in path.parts
    ]

    syntax_failures = []
    for path in py_files:
        result = verify_file(path)
        if result.success:
            continue
        syntax_failures.append(
            {
                "file": path.relative_to(root).as_posix(),
                "issues": [
                    check.message
                    for check in result.checks
                    if not check.ok
                ],
            }
        )

    profile = load_profile(config.migration.profile)
    rules_path = list(rules_paths_for_profile(profile.rules))
    unresolved_signals: list[dict] = []
    for path in py_files:
        unresolved_signals.extend(
            scan_python_signals(
                path.read_text(encoding="utf-8-sig", errors="ignore"),
                path.relative_to(root).as_posix(),
                rules_path=rules_path,
            )
        )

    behavior: dict = {"enabled": config.verification.enabled}
    if config.verification.enabled:
        result = run_behavior_verification(root, config.verification)
        behavior.update(
            {
                "success": result.success,
                "checks": [
                    {
                        "name": check.name,
                        "ok": check.ok,
                        "message": check.message,
                    }
                    for check in result.checks
                ],
            }
        )

    syntax_passed = len(py_files) - len(syntax_failures)
    syntax_rate = syntax_passed / len(py_files) if py_files else 1.0
    behavior_ok = behavior.get("success", True)
    overall_success = (
        syntax_rate == 1.0
        and not unresolved_signals
        and behavior_ok
    )
    return {
        "output_root": str(root),
        "profile": profile.name,
        "python_files": len(py_files),
        "syntax_passed": syntax_passed,
        "syntax_pass_rate": syntax_rate,
        "syntax_failures": syntax_failures,
        "unresolved_signal_count": len(unresolved_signals),
        "unresolved_signals": unresolved_signals,
        "behavior": behavior,
        "overall_success": overall_success,
    }
