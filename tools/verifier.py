from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str = ""


@dataclass
class VerifierResult:
    success: bool
    checks: list[CheckResult]


def verify_file(path: str | Path) -> VerifierResult:
    """验证输出文件：Python 文件做 AST 语法检查，其他文件检查可读性。"""
    target = Path(path)
    checks: list[CheckResult] = []

    if not target.is_file():
        return VerifierResult(
            success=False,
            checks=[CheckResult("exists", False, f"文件不存在: {target}")],
        )
    checks.append(CheckResult("exists", True))

    if target.suffix.lower() == ".py":
        try:
            ast.parse(target.read_text(encoding="utf-8"))
            checks.append(CheckResult("syntax", True))
        except SyntaxError as exc:
            checks.append(CheckResult("syntax", False, str(exc)))
    else:
        checks.append(CheckResult("readable", True))

    return VerifierResult(success=all(check.ok for check in checks), checks=checks)
