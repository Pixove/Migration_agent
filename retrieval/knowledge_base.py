from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.config import RetrievalConfig
from retrieval import HybridRetriever
from retrieval.documents import Document, load_documents


@dataclass
class KnowledgeBaseEntry:
    source: str
    sha256: str
    imported_at: str
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeBase:
    """持久化知识库：清单、内容哈希、增量导入与索引重建。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "kb.json"
        self._entries: dict[str, KnowledgeBaseEntry] = {}
        self._load()

    def import_source(self, source: str | Path) -> dict[str, int]:
        """导入文件或目录，按内容哈希跳过未变更文档。"""
        documents = load_documents(source)
        stats = {"added": 0, "updated": 0, "skipped": 0}
        for document in documents:
            key = f"{document.source}:{document.doc_id}"
            digest = _sha256(document.text)
            existing = self._entries.get(key)
            if existing is not None and existing.sha256 == digest:
                stats["skipped"] += 1
                continue

            self._entries[key] = KnowledgeBaseEntry(
                source=document.source,
                sha256=digest,
                imported_at=_now(),
                doc_id=document.doc_id,
                text=document.text,
                metadata=document.metadata,
            )
            if existing is None:
                stats["added"] += 1
            else:
                stats["updated"] += 1

        self.save()
        return stats

    def documents(self) -> list[Document]:
        return [
            Document(
                doc_id=entry.doc_id,
                text=entry.text,
                source=entry.source,
                metadata=entry.metadata,
            )
            for entry in self._entries.values()
        ]

    def build_retriever(self, config: RetrievalConfig) -> HybridRetriever:
        retriever = HybridRetriever(config)
        retriever.index(self.documents())
        return retriever

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "updated_at": _now(),
            "entries": {
                key: asdict(entry) for key, entry in self._entries.items()
            },
        }
        self.manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self.manifest_path.is_file():
            return
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        for key, raw in data.get("entries", {}).items():
            self._entries[key] = KnowledgeBaseEntry(**raw)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
