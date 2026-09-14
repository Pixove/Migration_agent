from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).parent / "rules" / "api_rules.yaml"


@dataclass
class CodeSignal:
    file: str
    line: int
    kind: str
    message: str


@dataclass(frozen=True)
class ApiRule:
    id: str
    kind: str
    type: str
    name: str
    message: str
    replacement: str = ""
    docs: str = ""
    alias: bool = False


_BUILTIN_RULES: tuple[ApiRule, ...] = (
    ApiRule(
        id="destructor",
        kind="destructor",
        type="function_def",
        name="__del__",
        message="__del__ 清理资源不可靠，建议改为上下文管理器",
    ),
    ApiRule(
        id="datetime_utcnow",
        kind="deprecated_time",
        type="call",
        name="datetime.utcnow",
        alias=True,
        replacement="datetime.now(timezone.utc)",
        message="datetime.utcnow 已废弃，建议使用 timezone-aware 时间",
    ),
    ApiRule(
        id="datetime_utcfromtimestamp",
        kind="deprecated_time",
        type="call",
        name="datetime.utcfromtimestamp",
        alias=True,
        replacement="datetime.fromtimestamp(..., tz=timezone.utc)",
        message="datetime.utcfromtimestamp 已废弃，建议使用 timezone-aware 时间",
    ),
    ApiRule(
        id="distutils",
        kind="removed_module",
        type="module",
        name="distutils",
        replacement="setuptools/packaging",
        message="distutils 已移除",
    ),
    ApiRule(
        id="imp",
        kind="removed_module",
        type="module",
        name="imp",
        replacement="importlib",
        message="imp 模块已移除",
    ),
)


@lru_cache(maxsize=8)
def load_api_rules(path: str | Path = RULES_PATH) -> tuple[ApiRule, ...]:
    """加载 API 规则表；规则文件缺失或为空时回退到内置规则。"""
    rules_path = Path(path)
    if not rules_path.is_file():
        return _BUILTIN_RULES
    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return _BUILTIN_RULES
    items = data.get("rules")
    if not isinstance(items, list):
        return _BUILTIN_RULES

    rules: list[ApiRule] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            rule = ApiRule(
                id=str(item["id"]),
                kind=str(item["kind"]),
                type=str(item["type"]),
                name=str(item["name"]),
                message=str(item["message"]),
                replacement=str(item.get("replacement", "")),
                docs=str(item.get("docs", "")),
                alias=bool(item.get("alias", False)),
            )
        except KeyError:
            continue
        rules.append(rule)
    return tuple(rules) or _BUILTIN_RULES


def _dotted_name(node: ast.AST) -> str | None:
    """把 Name/Attribute 节点还原为点分名称。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _matches(full_name: str | None, rule: ApiRule) -> bool:
    if not full_name:
        return False
    if full_name == rule.name:
        return True
    if full_name.endswith(f".{rule.name}"):
        return True
    if rule.alias:
        return full_name.split(".")[-1] == rule.name.split(".")[-1]
    return False


class _SignalVisitor(ast.NodeVisitor):
    def __init__(self, rules: tuple[ApiRule, ...]) -> None:
        self.rules = rules
        self.signals: list[dict[str, Any]] = []
        self._seen: set[tuple[int, str, str]] = set()

    def _add(self, node: ast.AST, rule: ApiRule) -> None:
        key = (getattr(node, "lineno", 0), rule.kind, rule.id)
        if key in self._seen:
            return
        self._seen.add(key)
        signal: dict[str, Any] = {
            "line": getattr(node, "lineno", 0),
            "kind": rule.kind,
            "message": rule.message,
            "api": rule.name,
        }
        if rule.replacement:
            signal["replacement"] = rule.replacement
        if rule.docs:
            signal["docs"] = rule.docs
        self.signals.append(signal)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        for rule in self.rules:
            if rule.type == "function_def" and node.name == rule.name:
                self._add(node, rule)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        full_name = _dotted_name(node.func)
        for rule in self.rules:
            if rule.type == "call" and _matches(full_name, rule):
                self._add(node, rule)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        full_name = _dotted_name(node)
        for rule in self.rules:
            if rule.type == "attribute" and _matches(full_name, rule):
                self._add(node, rule)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        for rule in self.rules:
            if rule.type == "attribute" and _matches(node.id, rule):
                self._add(node, rule)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            for rule in self.rules:
                if rule.type != "module":
                    continue
                if alias.name == rule.name or alias.name.startswith(
                    f"{rule.name}."
                ):
                    self._add(node, rule)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for rule in self.rules:
            if rule.type != "module":
                continue
            if module == rule.name or module.startswith(f"{rule.name}."):
                self._add(node, rule)
        self.generic_visit(node)


def scan_python_signals(
    source_text: str,
    file: str,
    rules_path: str | Path | None = None,
) -> list[dict]:
    """按规则表扫描 Python 源码中的迁移信号。"""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []
    rules = load_api_rules(rules_path or RULES_PATH)
    visitor = _SignalVisitor(rules)
    visitor.visit(tree)
    return [
        {"file": file, **signal}
        for signal in visitor.signals
    ]
