from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from retrieval import HybridRetriever
from retrieval.bm25 import BM25Retriever
from retrieval.documents import Document, load_documents
from retrieval.embeddings import VectorRetriever
from retrieval import RetrievalHit
from retrieval.reranker import Reranker


class BM25Tests(unittest.TestCase):
    def test_relevant_doc_ranks_first(self):
        docs = [
            Document("d1", "Python 2 uses print statement syntax."),
            Document("d2", "Python 3 uses print function with parentheses."),
            Document("d3", "Database connection pooling details."),
        ]
        retriever = BM25Retriever()
        retriever.index(docs)
        hits = retriever.search("print statement")
        self.assertEqual(hits[0][0].doc_id, "d1")

    def test_empty_corpus_returns_empty(self):
        retriever = BM25Retriever()
        retriever.index([])
        self.assertEqual(retriever.search("print"), [])

    def test_chinese_query_ranks_matching_doc_first(self):
        docs = [
            Document("d1", "内存泄漏修复指南：引用环会导致对象无法回收。"),
            Document("d2", "并发安全最佳实践：使用锁保护共享状态。"),
        ]
        retriever = BM25Retriever()
        retriever.index(docs)
        hits = retriever.search("内存泄漏 引用环")
        self.assertEqual(hits[0][0].doc_id, "d1")


class VectorRetrieverTests(unittest.TestCase):
    def test_disabled_returns_empty(self):
        retriever = VectorRetriever("text-embedding-3-small", enabled=False)
        retriever.index([Document("d1", "hello world")])
        self.assertEqual(retriever.search("hello"), [])


class RerankerTests(unittest.TestCase):
    def test_disabled_keeps_original_order(self):
        reranker = Reranker("cross-encoder/ms-marco-MiniLM-L-6-v2", enabled=False)
        doc_a = Document("a", "text a")
        doc_b = Document("b", "text b")
        result = reranker.rerank("query", [(doc_a, 0.9), (doc_b, 0.5)])
        self.assertEqual([item.document.doc_id for item in result], ["a", "b"])
        self.assertEqual([item.score for item in result], [0.9, 0.5])


class DocumentLoaderTests(unittest.TestCase):
    def test_load_txt_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide.txt"
            path.write_text("迁移最佳实践\n", encoding="utf-8")
            docs = load_documents(path)
            self.assertEqual(len(docs), 1)
            self.assertIn("迁移最佳实践", docs[0].text)


class HybridRetrieverTests(unittest.TestCase):
    def test_uses_bm25_when_vector_disabled(self):
        config = load_config("config.yaml").retrieval
        hybrid = HybridRetriever(config)
        docs = [
            Document("d1", "Python 2 uses print statement syntax."),
            Document("d2", "unrelated content"),
        ]
        hybrid.index(docs)
        hits = hybrid.search("print statement")
        self.assertTrue(hits)
        self.assertEqual(hits[0].document.doc_id, "d1")
        self.assertIn(hits[0].source, {"bm25", "rerank"})

    def test_rrf_keeps_strong_bm25_hit_after_rerank(self):
        def hit(doc_id, source, score):
            return RetrievalHit(Document(doc_id, "text"), score, source)

        bm25 = [
            hit("d1", "bm25", 10.0),
            hit("d2", "bm25", 2.0),
            hit("d3", "bm25", 1.0),
        ]
        reranked = [
            hit("d3", "rerank", 9.0),
            hit("d2", "rerank", 8.0),
            hit("d1", "rerank", 6.0),
        ]
        merged = HybridRetriever._rrf_merge(
            bm25,
            [],
            reranked,
            limit=2,
        )
        # BM25 第一的 d1 虽被重排到第三，仍通过 RRF 保留在 Top-2。
        self.assertEqual([item.document.doc_id for item in merged], ["d1", "d3"])


if __name__ == "__main__":
    unittest.main()
