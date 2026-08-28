from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.dispatcher import ToolDispatcher
from agent.guardrails import PathGuard, ToolRegistry
from agent.tooling import ToolContext, register_tools

EDIT_ITEM = {
    "file": "a.py",
    "start_line": 1,
    "end_line": 1,
    "new_content": "x = 2\n",
    "reason": "semantic edit",
    "evidence": {"doc_id": "d1"},
    "impact": "low",
}


class EditToolTests(unittest.TestCase):
    def _build(self, tmp: str):
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
        return dispatcher, output

    def test_propose_edit_returns_preview_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, output = self._build(tmp)
            result = dispatcher.call("propose_edit", item=EDIT_ITEM)
            self.assertTrue(result.success)
            self.assertIn("x = 2", result.result["preview"])
            self.assertFalse((output / "a.py").exists())

    def test_apply_edit_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, output = self._build(tmp)
            result = dispatcher.call("apply_edit", item=EDIT_ITEM)
            self.assertTrue(result.success)
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 2\n",
            )

    def test_edit_without_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, _ = self._build(tmp)
            item = dict(EDIT_ITEM)
            del item["evidence"]
            result = dispatcher.call("apply_edit", item=item)
            self.assertFalse(result.success)

    def test_invalid_line_range_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, _ = self._build(tmp)
            item = dict(EDIT_ITEM)
            item["start_line"] = 5
            result = dispatcher.call("apply_edit", item=item)
            self.assertFalse(result.success)

    def test_replacement_alias_and_whole_file_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, output = self._build(tmp)
            item = {
                "file": "a.py",
                "replacement": "x = 99\n",
                "reason": "semantic",
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            result = dispatcher.call("apply_edit", item=item)
            self.assertTrue(result.success)
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 99\n",
            )

    def test_string_evidence_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, output = self._build(tmp)
            item = dict(EDIT_ITEM)
            item["evidence"] = "知识库说明：建议使用上下文管理器"
            result = dispatcher.call("apply_edit", item=item)
            self.assertTrue(result.success)
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 2\n",
            )

    def test_end_line_clamped_to_file_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            dispatcher, output = self._build(tmp)
            item = dict(EDIT_ITEM)
            item["start_line"] = 1
            item["end_line"] = 6
            result = dispatcher.call("apply_edit", item=item)
            self.assertTrue(result.success)
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 2\n",
            )

    def test_apply_edit_is_incremental_over_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text(
                "class A:\n"
                "    def __del__(self):\n"
                "        pass\n"
                "    def opened_at(self):\n"
                "        return datetime.utcnow()\n",
                encoding="utf-8",
            )
            config = load_config("config.yaml")
            ctx = ToolContext(config=config, guard=PathGuard(source, output))
            dispatcher = ToolDispatcher(
                ToolRegistry(config.guardrails.allowed_tools)
            )
            register_tools(dispatcher, ctx)

            first = {
                "file": "a.py",
                "start_line": 2,
                "end_line": 3,
                "new_content": (
                    "    def __enter__(self):\n"
                    "        return self\n"
                    "    def __exit__(self, exc_type, exc_val, exc_tb):\n"
                    "        self.close()\n"
                ),
                "evidence": {"kind": "destructor"},
                "impact": "low",
            }
            second = {
                "file": "a.py",
                "start_line": 7,
                "end_line": 7,
                "new_content": (
                    "        return datetime.now(datetime.timezone.utc)\n"
                ),
                "evidence": {"kind": "deprecated_time"},
                "impact": "low",
            }
            self.assertTrue(dispatcher.call("apply_edit", item=first).success)
            preview = dispatcher.call("propose_edit", item=second)
            self.assertTrue(preview.success)
            self.assertNotIn("__del__", preview.result["diff"])
            self.assertTrue(dispatcher.call("apply_edit", item=second).success)
            text = (output / "a.py").read_text(encoding="utf-8")
            self.assertNotIn("__del__", text)
            self.assertNotIn("utcnow", text)
            self.assertIn("datetime.timezone.utc", text)


if __name__ == "__main__":
    unittest.main()
