from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.config import load_config
from retrieval.documents import Document, RetrievalError
from retrieval.embeddings import VectorRetriever


class VectorRetrieverChromaTests(unittest.TestCase):
    def test_missing_embedding_dependency_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            retriever = VectorRetriever(
                "some-model",
                enabled=True,
                chroma_path=str(Path(tmp) / "chroma"),
            )
            with patch.dict(
                "sys.modules",
                {"sentence_transformers": None},
            ):
                with self.assertRaises(RetrievalError):
                    retriever.index([Document("d1", "hello")])

    def test_disabled_returns_empty(self):
        retriever = VectorRetriever("some-model", enabled=False)
        retriever.index([Document("d1", "hello")])
        self.assertEqual(retriever.search("hello"), [])


class VectorConfigTests(unittest.TestCase):
    def test_default_chroma_path(self):
        config = load_config("config.yaml")
        self.assertEqual(config.retrieval.vector_chroma_path, "kb/chroma")


if __name__ == "__main__":
    unittest.main()
