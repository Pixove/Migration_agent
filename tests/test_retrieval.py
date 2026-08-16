from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from retrieval import HybridRetriever
from retrieval.bm25 import BM25Retriever
from retrieval.documents import Document, load_documents
from retrieval.embeddings import VectorRetriever
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


if __name__ == "__main__":
    unittest.main()
