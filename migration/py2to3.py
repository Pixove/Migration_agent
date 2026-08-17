from __future__ import annotations

import re
from typing import Any

_PRINT_STATEMENT = re.compile(r"^(?P<indent>[ \t]*)print (?P<body>.*)$")
_EXCEPT_CLAUSE = re.compile(
    r"^(?P<indent>[ \t]*)except\s+"
    r"(?P<exc>[A-Za-z_][A-Za-z0-9_.]*)\s*,\s*"
    r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)(?P<suffix>\s*:.*)$"
)
_XRANGE_CALL = re.compile(r"\bxrange\(")
_RAW_INPUT_CALL = re.compile(r"\braw_input\(")
_LONG_CALL = re.compile(r"\blong\(")
_UNICODE_CALL = re.compile(r"\bunicode\(")
_BASESTRING = re.compile(r"\bbasestring\b")
_UNICODE_LITERAL = re.compile(r"(?<!\w)u(['\"])")


def transform_python2_to_3(source_text: str, item: Any = None) -> str:
    """将常见 Python 2 语法改写为 Python 3 等价语法。"""
    lines = source_text.splitlines(keepends=True)
    return "".join(_transform_line(line) for line in lines)


def _transform_line(line: str) -> str:
    line = _transform_except_clause(line)
    line = _transform_print_statement(line)
    line = _XRANGE_CALL.sub("range(", line)
    line = _RAW_INPUT_CALL.sub("input(", line)
    line = _LONG_CALL.sub("int(", line)
    line = _UNICODE_CALL.sub("str(", line)
    line = _BASESTRING.sub("str", line)
    line = _UNICODE_LITERAL.sub(r"\1", line)
    return line


def _transform_except_clause(line: str) -> str:
    match = _EXCEPT_CLAUSE.match(line)
    if match is None:
        return line
    newline = "\n" if line.endswith("\n") else ""
    return (
        f"{match.group('indent')}except {match.group('exc')} as "
        f"{match.group('var')}{match.group('suffix')}{newline}"
    )


def _transform_print_statement(line: str) -> str:
    match = _PRINT_STATEMENT.match(line)
    if match is None:
        return line

    body = match.group("body")
    if body.startswith("("):
        return line

    comment = ""
    if "#" in body:
        body, comment = body.split("#", 1)
        comment = "#" + comment

    newline = "\n" if line.endswith("\n") else ""
    rendered = f"{match.group('indent')}print({body.rstrip()})"
    if comment:
        rendered += f" {comment.rstrip()}"
    return rendered + newline
