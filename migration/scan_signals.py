from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class CodeSignal:
    file: str
    line: int
    kind: str
    message: str


class _SignalVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.signals: list[tuple[int, str, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "__del__":
            self.signals.append(
                (
                    node.lineno,
                    "destructor",
                    "__del__ 清理资源不可靠，建议改为上下文管理器",
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            value = node.func.value
            is_datetime = (
                isinstance(value, ast.Attribute) and value.attr == "datetime"
            ) or (
                isinstance(value, ast.Name) and value.id == "datetime"
            )
            if is_datetime and node.func.attr in (
                "utcnow",
                "utcfromtimestamp",
            ):
                self.signals.append(
                    (
                        node.lineno,
                        "deprecated_time",
                        f"datetime.{node.func.attr} 已废弃，"
                        "建议使用 timezone-aware 时间",
                    )
                )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root == "distutils":
                self.signals.append(
                    (node.lineno, "removed_module", "distutils 已移除")
                )
            elif root == "imp":
                self.signals.append(
                    (node.lineno, "removed_module", "imp 模块已移除")
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".")[0]
        if root == "distutils":
            self.signals.append(
                (node.lineno, "removed_module", "distutils 已移除")
            )
        elif root == "imp":
            self.signals.append(
                (node.lineno, "removed_module", "imp 模块已移除")
            )
        self.generic_visit(node)


def scan_python_signals(source_text: str, file: str) -> list[dict]:
    """扫描 Python 源码中的可疑迁移信号。"""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []
    visitor = _SignalVisitor()
    visitor.visit(tree)
    return [
        {"file": file, "line": line, "kind": kind, "message": message}
        for line, kind, message in visitor.signals
    ]
