from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RetrievalError(Exception):
    """检索层错误。"""


@dataclass
class Document:
    doc_id: str
    text: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def load_documents(source: str | Path) -> list[Document]:
    """从文件或目录加载文档，支持 TXT、Markdown 与 PDF。"""
    path = Path(source)
    if path.is_file():
        return _load_file(path)
    if path.is_dir():
        docs: list[Document] = []
        supported = {".txt", ".md", ".pdf"}
        for file in sorted(path.rglob("*")):
            if file.is_file() and file.suffix.lower() in supported:
                docs.extend(_load_file(file))
        return docs
    raise RetrievalError(f"文档来源不存在: {path}")


def _load_file(path: Path) -> list[Document]:
    if path.suffix.lower() == ".pdf":
        return _load_pdf(path)
    return [_load_text(path)]


def _load_text(path: Path) -> Document:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return Document(doc_id=path.stem, text=text, source=str(path))


def _load_pdf(path: Path) -> list[Document]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RetrievalError(
            "未安装 pypdf，PDF 解析请先执行: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))
    docs: list[Document] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        docs.append(
            Document(
                doc_id=f"{path.stem}-p{index}",
                text=text,
                source=str(path),
                metadata={"page": index},
            )
        )
    return docs
