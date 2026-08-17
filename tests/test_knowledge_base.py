from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from retrieval.knowledge_base import KnowledgeBase


class KnowledgeBaseTests(unittest.TestCase):
    def test_import_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb_root = Path(tmp) / "kb"
            doc_dir = Path(tmp) / "docs"
            doc_dir.mkdir()
            (doc_dir / "guide.txt").write_text("best practice\n", encoding="utf-8")

            kb = KnowledgeBase(kb_root)
            stats = kb.import_source(doc_dir)
            self.assertEqual(stats["added"], 1)
            self.assertEqual(len(kb.documents()), 1)

            reloaded = KnowledgeBase(kb_root)
            self.assertEqual(len(reloaded.documents()), 1)

    def test_incremental_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb_root = Path(tmp) / "kb"
            doc_path = Path(tmp) / "guide.txt"
            doc_path.write_text("v1\n", encoding="utf-8")

            kb = KnowledgeBase(kb_root)
            self.assertEqual(kb.import_source(doc_path)["added"], 1)
            self.assertEqual(kb.import_source(doc_path)["skipped"], 1)

            doc_path.write_text("v2\n", encoding="utf-8")
            self.assertEqual(kb.import_source(doc_path)["updated"], 1)

    def test_build_retriever(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb_root = Path(tmp) / "kb"
            doc_path = Path(tmp) / "guide.txt"
            doc_path.write_text(
                "Python 2 print statement migration\n",
                encoding="utf-8",
            )

            kb = KnowledgeBase(kb_root)
            kb.import_source(doc_path)
            config = load_config("config.yaml").retrieval
            retriever = kb.build_retriever(config)
            hits = retriever.search("print statement")
            self.assertTrue(hits)

    def test_builtin_knowledge_base_imports_and_searches(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = KnowledgeBase(Path(tmp) / "kb")
            stats = kb.import_source("knowledge_base")
            self.assertGreater(stats["added"], 5)

            config = load_config("config.yaml").retrieval
            hits = kb.build_retriever(config).search("print 语句 迁移")
            self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
