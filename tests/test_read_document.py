from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.dispatcher import ToolDispatcher
from agent.guardrails import PathGuard, ToolRegistry
from agent.tooling import ToolContext, register_tools


class ReadDocumentToolTests(unittest.TestCase):
    def _build_dispatcher(self, tmp: str) -> ToolDispatcher:
        source = Path(tmp) / "src"
        output = Path(tmp) / "out"
        source.mkdir()
        config = load_config("config.yaml")
        ctx = ToolContext(config=config, guard=PathGuard(source, output))
        dispatcher = ToolDispatcher(ToolRegistry(config.guardrails.allowed_tools))
        register_tools(dispatcher, ctx)
        return dispatcher

    def test_reads_allowed_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build_dispatcher(tmp)
            result = dispatcher.call(
                "read_document",
                path="rules/03_迁移决策规范.md",
            )
            self.assertTrue(result.success)
            self.assertIn("证据", result.result["content"])

    def test_escape_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build_dispatcher(tmp)
            result = dispatcher.call(
                "read_document",
                path="../config.yaml",
            )
            self.assertFalse(result.success)
            self.assertIn("config.yaml", result.error)

    def test_absolute_path_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build_dispatcher(tmp)
            result = dispatcher.call(
                "read_document",
                path="C:/Windows/win.ini",
            )
            self.assertFalse(result.success)

    def test_docs_not_readable_by_runtime_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build_dispatcher(tmp)
            result = dispatcher.call(
                "read_document",
                path="docs/06_评估系统.md",
            )
            self.assertFalse(result.success)

    def test_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build_dispatcher(tmp)
            result = dispatcher.call(
                "read_document",
                path="rules/03_迁移决策规范.md",
                max_chars=20,
            )
            self.assertTrue(result.success)
            self.assertTrue(result.result["truncated"])
            self.assertLessEqual(len(result.result["content"]), 20)

    def test_allowed_tools_contains_read_document(self):
        config = load_config("config.yaml")
        self.assertIn("read_document", config.guardrails.allowed_tools)


if __name__ == "__main__":
    unittest.main()
