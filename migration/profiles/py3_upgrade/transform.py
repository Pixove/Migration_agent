from __future__ import annotations

import ast
from typing import Any

_TYPING_TO_BUILTIN = {
    "Dict": "dict",
    "List": "list",
    "Tuple": "tuple",
    "Set": "set",
    "Type": "type",
}

_DEPRECATED_CALLS = {
    "utcnow": "datetime.utcnow 已废弃，建议使用 timezone-aware 时间",
    "utcfromtimestamp": "datetime.utcfromtimestamp 已废弃，建议使用 timezone-aware 时间",
}


class _UpgradeVisitor(ast.NodeVisitor):
    """收集安全的 AST 改写与废弃 API 标注。"""

    def __init__(self) -> None:
        self.replacements: list[tuple[int, int, int, str]] = []
        self.todos: dict[int, str] = {}
        self._typing_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root == "distutils":
                self.todos[node.lineno] = (
                    "distutils 已移除，请迁移到 setuptools 等替代方案"
                )
            elif root == "imp":
                self.todos[node.lineno] = (
                    "imp 模块已移除，请迁移到 importlib"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module == "typing":
            for alias in node.names:
                if alias.name in _TYPING_TO_BUILTIN:
                    self._typing_names.add(alias.name)
        root = module.split(".")[0]
        if root == "distutils":
            self.todos[node.lineno] = (
                "distutils 已移除，请迁移到 setuptools 等替代方案"
            )
        elif root == "imp":
            self.todos[node.lineno] = (
                "imp 模块已移除，请迁移到 importlib"
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self._typing_names and node.end_col_offset is not None:
            self.replacements.append(
                (
                    node.lineno,
                    node.col_offset,
                    node.end_col_offset,
                    _TYPING_TO_BUILTIN[node.id],
                )
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "typing"
            and node.attr in _TYPING_TO_BUILTIN
            and node.end_col_offset is not None
        ):
            self.replacements.append(
                (
                    node.lineno,
                    node.col_offset,
                    node.end_col_offset,
                    _TYPING_TO_BUILTIN[node.attr],
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
            if is_datetime and node.func.attr in _DEPRECATED_CALLS:
                self.todos[node.lineno] = _DEPRECATED_CALLS[node.func.attr]
            elif (
                isinstance(value, ast.Name)
                and value.id == "asyncio"
                and node.func.attr == "get_event_loop"
            ):
                self.todos[node.lineno] = (
                    "asyncio.get_event_loop 已废弃，"
                    "请改用 asyncio.get_running_loop 或显式事件循环"
                )
        self.generic_visit(node)


def transform_py3_upgrade(source_text: str, item: Any = None) -> str:
    """基于 AST 的 Python 3.x 升级转换。

    安全改写 typing 类型别名，并对废弃 API 添加 TODO 标注。
    """
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return source_text

    visitor = _UpgradeVisitor()
    visitor.visit(tree)
    result = _apply_replacements(source_text, visitor.replacements)
    return _add_todo_comments(result, visitor.todos)


def _apply_replacements(
    text: str,
    replacements: list[tuple[int, int, int, str]],
) -> str:
    if not replacements:
        return text

    lines = text.splitlines(keepends=True)
    offsets: dict[int, int] = {}
    offset = 0
    for index, line in enumerate(lines, start=1):
        offsets[index] = offset
        offset += len(line)

    for lineno, col, end_col, new in sorted(
        replacements,
        key=lambda item: item[0],
        reverse=True,
    ):
        start = offsets[lineno] + col
        end = offsets[lineno] + end_col
        text = text[:start] + new + text[end:]
    return text


def _add_todo_comments(text: str, todos: dict[int, str]) -> str:
    if not todos:
        return text

    lines = text.splitlines(keepends=True)
    for lineno in sorted(todos, reverse=True):
        line = lines[lineno - 1]
        had_newline = line.endswith("\n")
        stripped = line.rstrip("\r\n")
        if "TODO(migration)" in stripped:
            continue
        lines[lineno - 1] = (
            stripped
            + f"  # TODO(migration): {todos[lineno]}"
            + ("\n" if had_newline else "")
        )
    return "".join(lines)
