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

DOCUMENT_INDEX = [
    ("rules/00_总则.md", "项目定位、规则优先级、基本原则"),
    ("rules/01_路径与权限边界.md", "输入只读、输出唯一可写、路径沙箱"),
    ("rules/02_工具使用规范.md", "工具白名单与调用约束"),
    ("rules/03_迁移决策规范.md", "证据要求、影响面、审批"),
    ("rules/04_验证与回滚规范.md", "应用后验证、失败回滚"),
    ("rules/05_审计与报告规范.md", "审计目录、报告要求"),
    ("skills/01_遗留代码扫描.md", "扫描与识别遗留代码"),
    ("skills/02_混合检索.md", "文档导入、BM25、向量、重排"),
    ("skills/03_迁移规划.md", "生成并校验迁移计划"),
    ("skills/04_补丁应用.md", "在输出目录应用计划"),
    ("skills/05_验证与报告.md", "验证输出并生成报告"),
]

RED_LINES = [
    "输入项目只读，绝不修改；输出目录唯一可写，绝不越界",
    "只允许调用白名单工具，禁止直接执行 shell 或读写文件",
    "transform 必须携带关联检索命中的证据",
    "验证失败的输出不得标记 applied，必须回滚",
    "禁止删除任何文件、禁止写入 API Key、禁止跳过审计",
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


def build_document_index() -> str:
    """生成紧凑的可用文档索引，供模型按需读取。"""
    lines = ["可用文档索引（需要时调用 read_document 读取全文）："]
    for path, description in DOCUMENT_INDEX:
        lines.append(f"- {path}  {description}")
    return "\n".join(lines)


def build_red_lines() -> str:
    """生成必须常驻的红线摘要。"""
    lines = ["红线（必须遵守，不可省略）："]
    lines.extend(f"- {rule}" for rule in RED_LINES)
    return "\n".join(lines)
