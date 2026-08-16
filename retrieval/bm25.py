from __future__ import annotations

import math
import re
from collections import Counter

from retrieval.documents import Document

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """轻量分词：小写化后提取字母、数字与下划线片段。"""
    return _TOKEN_RE.findall(text.lower())


class BM25Retriever:
    """纯 Python 实现的 BM25 关键词检索，骨架阶段不依赖外部库。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[Document] = []
        self._term_freqs: list[Counter[str]] = []
        self._idf: dict[str, float] = {}
        self._avgdl: float = 0.0

    def index(self, docs: list[Document]) -> None:
        self._docs = list(docs)
        self._term_freqs = [Counter(tokenize(doc.text)) for doc in self._docs]

        doc_count = len(self._docs)
        if doc_count == 0:
            self._idf = {}
            self._avgdl = 0.0
            return

        total_length = sum(sum(freqs.values()) for freqs in self._term_freqs)
        self._avgdl = total_length / doc_count

        document_freq = Counter()
        for freqs in self._term_freqs:
            for term in freqs:
                document_freq[term] += 1

        self._idf = {
            term: math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in document_freq.items()
        }

    def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        if not self._docs:
            return []

        query_terms = tokenize(query)
        scores: list[tuple[Document, float]] = []

        for doc, freqs in zip(self._docs, self._term_freqs):
            doc_length = sum(freqs.values())
            score = 0.0
            for term in query_terms:
                if term not in self._idf or term not in freqs:
                    continue
                term_freq = freqs[term]
                if self._avgdl > 0:
                    denom = term_freq + self.k1 * (
                        1 - self.b + self.b * (doc_length / self._avgdl)
                    )
                else:
                    denom = term_freq + self.k1
                score += self._idf[term] * (term_freq * (self.k1 + 1)) / denom
            scores.append((doc, score))

        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores[:top_k]
