from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.dispatcher import ToolDispatcher
from agent.guardrails import PathGuard, ToolRegistry
from agent.tooling import ToolContext, register_tools


class ReadSourceToolTests(unittest.TestCase):
    def _build(self, tmp: str) -> ToolDispatcher:
        source = Path(tmp) / "src"
        output = Path(tmp) / "out"
        source.mkdir()
        (source / "a.py").write_text("x = 1\n", encoding="utf-8")
        config = load_config("config.yaml")
        ctx = ToolContext(config=config, guard=PathGuard(source, output))
        dispatcher = ToolDispatcher(
            ToolRegistry(config.guardrails.allowed_tools)
        )
        register_tools(dispatcher, ctx)
        return dispatcher

    def test_reads_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build(tmp)
            result = dispatcher.call("read_source", path="a.py")
            self.assertTrue(result.success)
            self.assertIn("x = 1", result.result["content"])

    def test_escape_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher = self._build(tmp)
            result = dispatcher.call("read_source", path="../config.yaml")
            self.assertFalse(result.success)

    def test_allowed_tools_contains_read_source(self):
        config = load_config("config.yaml")
        self.assertIn("read_source", config.guardrails.allowed_tools)


if __name__ == "__main__":
    unittest.main()
