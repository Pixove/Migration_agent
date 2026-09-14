from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
            ast.parse(target.read_text(encoding="utf-8-sig"))
            checks.append(CheckResult("syntax", True))
        except SyntaxError as exc:
            checks.append(CheckResult("syntax", False, str(exc)))
    else:
        checks.append(CheckResult("readable", True))

    return VerifierResult(success=all(check.ok for check in checks), checks=checks)


_MODULE_NAME_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


def run_behavior_verification(
    output_root: str | Path,
    config: Any,
) -> VerifierResult:
    """在输出目录执行 import 检查与配置的白名单命令。"""
    if not config.enabled:
        return VerifierResult(
            success=True,
            checks=[CheckResult("behavior", True, "行为验证未启用")],
        )

    root = Path(output_root)
    if not root.is_dir():
        return VerifierResult(
            success=False,
            checks=[CheckResult("output", False, f"输出目录不存在: {root}")],
        )

    checks: list[CheckResult] = []
    timeout = max(1, int(config.timeout_seconds))
    python_executable, target_check = _resolve_python_executable(config)
    if target_check is not None:
        checks.append(target_check)

    for file_name in config.required_files:
        checks.append(_check_required_file(root, str(file_name)))

    if config.required_packages:
        if python_executable is None:
            checks.append(
                CheckResult(
                    "packages",
                    False,
                    "target_python 不可用，未执行依赖检查",
                )
            )
        else:
            for package in config.required_packages:
                checks.append(
                    _check_required_package(
                        str(package),
                        python_executable,
                        cwd=root,
                        timeout=timeout,
                    )
                )

    if config.import_modules:
        if python_executable is None:
            checks.append(
                CheckResult(
                    "imports",
                    False,
                    "target_python 不可用，未执行导入检查",
                )
            )
        else:
            for module in config.import_modules:
                name = f"import:{module}"
                if not _MODULE_NAME_RE.match(str(module)):
                    checks.append(
                        CheckResult(name, False, f"非法模块名: {module}")
                    )
                    continue
                checks.append(
                    _run_command_check(
                        name,
                        [python_executable, "-c", f"import {module}"],
                        cwd=root,
                        timeout=timeout,
                    )
                )

    for command in config.commands:
        parts = _split_command(str(command))
        if not parts:
            checks.append(
                CheckResult("command", False, f"空命令: {command}")
            )
            continue
        if _is_bare_python_command(parts):
            checks.append(
                CheckResult(
                    f"command:{command}",
                    False,
                    "Python 命令缺少 -c/-m 或脚本路径",
                )
            )
            continue
        checks.append(
            _run_command_check(
                f"command:{command}",
                parts,
                cwd=root,
                timeout=timeout,
            )
        )

    if not checks:
        checks.append(CheckResult("behavior", True, "未配置行为验证项"))
    return VerifierResult(
        success=all(check.ok for check in checks),
        checks=checks,
    )


def _check_required_file(root: Path, name: str) -> CheckResult:
    raw = Path(name)
    if raw.is_absolute() or ".." in raw.parts:
        return CheckResult(
            f"file:{name}",
            False,
            "必需文件必须是输出目录内的相对路径",
        )
    target = (root / raw).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return CheckResult(f"file:{name}", False, "文件路径越界")
    if not target.is_file():
        return CheckResult(f"file:{name}", False, "文件不存在")
    return CheckResult(f"file:{name}", True)


def _resolve_python_executable(
    config: Any,
) -> tuple[str | None, CheckResult | None]:
    configured = str(getattr(config, "target_python", "") or "").strip()
    if not configured:
        return sys.executable, None

    target = Path(os.path.expandvars(configured)).expanduser()
    if not target.is_file():
        return (
            None,
            CheckResult(
                "python:target",
                False,
                f"目标解释器不存在: {target}",
            ),
        )
    return str(target), CheckResult("python:target", True, str(target))


def _check_required_package(
    name: str,
    python_executable: str,
    *,
    cwd: Path,
    timeout: int,
) -> CheckResult:
    code = (
        "from importlib import metadata; "
        f"print(metadata.version({name!r}))"
    )
    return _run_command_check(
        f"package:{name}",
        [python_executable, "-c", code],
        cwd=cwd,
        timeout=timeout,
    )


def _split_command(command: str) -> list[str]:
    parts = shlex.split(command, posix=False)
    return [
        part[1:-1]
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'"
        else part
        for part in parts
    ]


def _run_command_check(
    name: str,
    parts: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> CheckResult:
    try:
        result = subprocess.run(
            parts,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name, False, f"验证超时（{timeout} 秒）")
    except OSError as exc:
        return CheckResult(name, False, f"验证命令执行失败: {exc}")

    if result.returncode == 0:
        return CheckResult(name, True)
    output = (result.stderr or result.stdout or "").strip()
    return CheckResult(
        name,
        False,
        f"退出码 {result.returncode}: {output[:500]}",
    )


def _is_bare_python_command(parts: list[str]) -> bool:
    if len(parts) != 1:
        return False
    name = Path(parts[0]).stem.lower()
    return name.startswith("python")
