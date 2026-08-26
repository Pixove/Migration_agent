"""RAG 混合检索层。"""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import RetrievalConfig
from retrieval.bm25 import BM25Retriever
from retrieval.documents import Document
from retrieval.embeddings import VectorRetriever
from retrieval.reranker import Reranker


@dataclass
class RetrievalHit:
    document: Document
    score: float
    source: str


class HybridRetriever:
    """BM25 与向量检索混合召回，再经过 Cross-Encoder 重排。"""

    def __init__(self, config: RetrievalConfig) -> None:
        self.bm25 = BM25Retriever() if config.bm25_enabled else None
        self.vector = VectorRetriever(
            config.embedding_model,
            config.vector_enabled,
            chroma_path=config.vector_chroma_path,
        )
        self.reranker = Reranker(config.rerank_model, config.rerank_enabled)
        self.bm25_top_k = config.bm25_top_k
        self.vector_top_k = config.vector_top_k
        self.rerank_top_k = config.rerank_top_k

    def index(self, docs: list[Document]) -> None:
        if self.bm25 is not None:
            self.bm25.index(docs)
        self.vector.index(docs)

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalHit]:
        candidates: list[RetrievalHit] = []
        if self.bm25 is not None:
            candidates.extend(
                RetrievalHit(document=doc, score=score, source="bm25")
                for doc, score in self.bm25.search(query, self.bm25_top_k)
            )
        candidates.extend(
            RetrievalHit(document=doc, score=score, source="vector")
            for doc, score in self.vector.search(query, self.vector_top_k)
        )

        merged = self._dedupe(candidates)
        if self.reranker is not None and merged:
            reranked = self.reranker.rerank(
                query,
                [(hit.document, hit.score) for hit in merged],
                top_k=self.rerank_top_k,
            )
            return [
                RetrievalHit(document=item.document, score=item.score, source="rerank")
                for item in reranked
            ]

        limit = top_k if top_k is not None else len(merged)
        return merged[:limit]

    @staticmethod
    def _dedupe(hits: list[RetrievalHit]) -> list[RetrievalHit]:
        best: dict[str, RetrievalHit] = {}
        for hit in hits:
            current = best.get(hit.document.doc_id)
            if current is None or hit.score > current.score:
                best[hit.document.doc_id] = hit
        return list(best.values())


__all__ = [
    "BM25Retriever",
    "Document",
    "HybridRetriever",
    "RetrievalHit",
    "Reranker",
    "VectorRetriever",
]
