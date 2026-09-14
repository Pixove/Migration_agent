from __future__ import annotations

import unittest
from pathlib import Path

from migration.scan_signals import scan_python_signals


class LangChainDemoTests(unittest.TestCase):
    def test_all_community_imports_produce_signals(self):
        source = Path("examples/langchain_legacy/app.py")
        text = source.read_text(encoding="utf-8")
        signals = scan_python_signals(text, "app.py")
        apis = {signal["api"] for signal in signals}
        self.assertGreaterEqual(len(signals), 15)
        self.assertIn(
            "langchain_community.vectorstores.Chroma",
            apis,
        )
        self.assertIn(
            "langchain_community.embeddings.HuggingFaceEmbeddings",
            apis,
        )
        self.assertIn(
            "langchain_community.chat_models.ChatOllama",
            apis,
        )


if __name__ == "__main__":
    unittest.main()
