from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RULES = [
    "rules/00_总则.md",
    "rules/01_路径与权限边界.md",
    "rules/02_工具使用规范.md",
    "rules/03_迁移决策规范.md",
    "rules/04_验证与回滚规范.md",
    "rules/05_审计与报告规范.md",
]

DEFAULT_SKILLS = [
    "skills/02_混合检索.md",
    "skills/03_迁移规划.md",
]


def load_project_documents(
    project_root: str | Path | None = None,
) -> dict[str, str]:
    """读取入口文件、规则与技能文档，缺失时跳过。"""
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    names = ["AGENTS.md", *DEFAULT_RULES, *DEFAULT_SKILLS]
    documents: dict[str, str] = {}
    for name in names:
        path = root / name
        if path.is_file():
            documents[name] = path.read_text(encoding="utf-8")
    return documents


def build_planning_context(project_root: str | Path | None = None) -> str:
    """组装供规划阶段使用的约束上下文。"""
    documents = load_project_documents(project_root)
    sections: list[str] = []

    entry = documents.get("AGENTS.md")
    if entry:
        sections.append(f"## Agent 入口\n{entry}")

    for name in DEFAULT_RULES:
        if name in documents:
            sections.append(f"## {name}\n{documents[name]}")

    for name in DEFAULT_SKILLS:
        if name in documents:
            sections.append(f"## {name}\n{documents[name]}")

    return "\n\n".join(sections)
