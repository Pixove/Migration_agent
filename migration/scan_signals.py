from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).parent / "rules" / "api_rules.yaml"
RULES_DIR = RULES_PATH.parent
VALID_RULE_TYPES = {
    "function_def",
    "call",
    "attribute",
    "module",
    "from_import",
}


def rules_paths_for_profile(
    profile_rules: list[str] | None = None,
) -> tuple[Path, ...]:
    """返回全局规则目录与档案专属规则的组合路径。"""
    paths = [RULES_DIR]
    for item in profile_rules or []:
        path = Path(item)
        if path not in paths:
            paths.append(path)
    return tuple(paths)


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
    module: str = ""
    package: str = ""
    deprecated_in: str = ""
    removed_in: str = ""
    severity: str = ""


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


@lru_cache(maxsize=16)
def load_api_rules(
    path: str | Path | tuple[str | Path, ...] | None = None,
) -> tuple[ApiRule, ...]:
    """加载并合并规则表；文件缺失或为空时回退到内置规则。"""
    rules_paths = _rule_files(path)
    if not rules_paths:
        return _BUILTIN_RULES

    rules: list[ApiRule] = []
    seen_ids: set[str] = set()
    for rules_path in rules_paths:
        for rule in _load_rule_file(rules_path):
            if rule.id in seen_ids:
                raise ValueError(
                    f"API 规则 ID 重复: {rule.id}（{rules_path}）"
                )
            seen_ids.add(rule.id)
            rules.append(rule)
    return tuple(rules) or _BUILTIN_RULES


def _rule_files(
    path: str | Path | tuple[str | Path, ...] | None,
) -> list[Path]:
    """规则路径为空时加载规则目录下的全部 YAML 文件。"""
    if path is None:
        return _expand_rule_path(RULES_DIR)
    if isinstance(path, (list, tuple)):
        files: list[Path] = []
        for item in path:
            files.extend(_expand_rule_path(Path(item)))
        return list(dict.fromkeys(files))
    return _expand_rule_path(Path(path))


def _expand_rule_path(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.glob("*.yaml")) + sorted(target.glob("*.yml"))
    if target.is_file():
        return [target]
    return []


def _load_rule_file(path: Path) -> list[ApiRule]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"读取 API 规则文件失败: {path}: {exc}") from exc
    items = data.get("rules")
    if not isinstance(items, list):
        raise ValueError(f"API 规则文件缺少 rules 列表: {path}")

    rules: list[ApiRule] = []
    for index, item in enumerate(items, start=1):
        rules.append(_parse_rule(item, path, index))
    return rules


def _parse_rule(item: Any, path: Path, index: int) -> ApiRule:
    if not isinstance(item, dict):
        raise ValueError(f"API 规则必须是对象: {path} 第 {index} 条")
    missing = [
        key
        for key in ("id", "kind", "type", "name", "message")
        if not item.get(key)
    ]
    if missing:
        raise ValueError(
            f"API 规则缺少字段 {missing}: {path} 第 {index} 条"
        )
    rule_type = str(item["type"])
    if rule_type not in VALID_RULE_TYPES:
        raise ValueError(
            f"API 规则 type 非法: {rule_type}（{path} 第 {index} 条），"
            f"可选: {sorted(VALID_RULE_TYPES)}"
        )
    module = str(item.get("module", ""))
    if rule_type == "from_import" and not module:
        raise ValueError(
            f"from_import 规则缺少 module: {path} 第 {index} 条"
        )
    if (
        str(item["kind"]) == "deprecated_api"
        and not item.get("replacement")
        and not item.get("docs")
    ):
        raise ValueError(
            f"deprecated_api 规则缺少 replacement 或 docs: "
            f"{path} 第 {index} 条"
        )
    return ApiRule(
        id=str(item["id"]),
        kind=str(item["kind"]),
        type=rule_type,
        name=str(item["name"]),
        message=str(item["message"]),
        replacement=str(item.get("replacement", "")),
        docs=str(item.get("docs", "")),
        alias=bool(item.get("alias", False)),
        module=module,
        package=str(item.get("package", "")),
        deprecated_in=str(item.get("deprecated_in", "")),
        removed_in=str(item.get("removed_in", "")),
        severity=str(item.get("severity", "")),
    )


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
            "api": (
                f"{rule.module}.{rule.name}"
                if rule.type == "from_import"
                else rule.name
            ),
        }
        for key in (
            "replacement",
            "docs",
            "package",
            "deprecated_in",
            "removed_in",
            "severity",
        ):
            value = getattr(rule, key)
            if value:
                signal[key] = value
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
            if rule.type == "module":
                if module == rule.name or module.startswith(f"{rule.name}."):
                    self._add(node, rule)
            elif rule.type == "from_import":
                if not (
                    module == rule.module
                    or module.startswith(f"{rule.module}.")
                ):
                    continue
                if any(alias.name == rule.name for alias in node.names):
                    self._add(node, rule)
        self.generic_visit(node)


def scan_python_signals(
    source_text: str,
    file: str,
    rules_path: str | Path | list[str | Path] | None = None,
) -> list[dict]:
    """按规则表扫描 Python 源码中的迁移信号。"""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []
    if isinstance(rules_path, list):
        rules_path = tuple(rules_path)
    rules = load_api_rules(rules_path)
    visitor = _SignalVisitor(rules)
    visitor.visit(tree)
    return [
        {"file": file, **signal}
        for signal in visitor.signals
    ]
