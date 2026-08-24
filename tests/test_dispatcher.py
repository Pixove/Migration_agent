from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.dispatcher import ToolDispatcher, ToolSpec
from agent.guardrails import Budget, GuardrailError, PathGuard, ToolRegistry
from agent.tooling import ToolContext, register_tools
from migration.py2to3 import transform_python2_to_3


class DispatcherMechanicsTests(unittest.TestCase):
    def test_whitelist_blocks_unknown_tool(self):
        registry = ToolRegistry(["hello"])
        dispatcher = ToolDispatcher(registry)
        dispatcher.register(ToolSpec("hello", "says hello", lambda: "hi"))

        result = dispatcher.call("hello")
        self.assertTrue(result.success)
        with self.assertRaises(GuardrailError):
            dispatcher.call("rm_all")

    def test_unregistered_tool_returns_failure(self):
        registry = ToolRegistry(["ghost"])
        dispatcher = ToolDispatcher(registry)
        result = dispatcher.call("ghost")
        self.assertFalse(result.success)
        self.assertIn("未注册", result.error)

    def test_call_limit_enforced(self):
        registry = ToolRegistry(["limited"])
        dispatcher = ToolDispatcher(registry)
        dispatcher.register(ToolSpec("limited", "x", lambda: 1, max_calls=1))

        self.assertTrue(dispatcher.call("limited").success)
        result = dispatcher.call("limited")
        self.assertFalse(result.success)
        self.assertIn("次数超过上限", result.error)

    def test_error_captured_in_result(self):
        def boom():
            raise ValueError("boom")

        registry = ToolRegistry(["boom"])
        dispatcher = ToolDispatcher(registry)
        dispatcher.register(ToolSpec("boom", "x", boom))

        result = dispatcher.call("boom")
        self.assertFalse(result.success)
        self.assertIn("boom", result.error)


class ToolingTests(unittest.TestCase):
    def test_scan_files_tool_returns_file_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            output.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")

            config = load_config("config.yaml")
            guard = PathGuard(source, output)
            ctx = ToolContext(
                config=config,
                guard=guard,
                transform=transform_python2_to_3,
            )
            dispatcher = ToolDispatcher(
                ToolRegistry(config.guardrails.allowed_tools),
                Budget(50, 3, 200),
            )
            register_tools(dispatcher, ctx)

            result = dispatcher.call("scan_files")
            self.assertTrue(result.success)
            self.assertEqual(
                [item["relative_path"] for item in result.result],
                ["a.py"],
            )
            self.assertEqual(len(ctx.files), 1)


if __name__ == "__main__":
    unittest.main()
