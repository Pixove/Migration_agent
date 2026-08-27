from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.agentic import AgenticRunner
from agent.config import load_config
from agent.llm import LLMError


class FakeAgentLLM:
    def __init__(self, decisions):
        self.decisions = decisions
        self.calls = 0

    def complete(self, messages, **kwargs):
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return json.dumps(decision, ensure_ascii=False)


class FlakyAgentLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, messages, **kwargs):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


class AgenticRunnerTests(unittest.TestCase):
    def test_agentic_retries_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            llm = FlakyAgentLLM(
                [
                    "not json",
                    json.dumps(
                        {
                            "thought": "完成",
                            "action": "finish",
                            "params": {},
                        }
                    ),
                ]
            )
            config = load_config("config.yaml")
            runner = AgenticRunner(config, source, output, llm=llm)
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertEqual(llm.calls, 2)

    def test_agentic_gives_up_after_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            llm = FlakyAgentLLM(["bad"] * 3)
            config = load_config("config.yaml")
            runner = AgenticRunner(config, source, output, llm=llm)
            with self.assertRaises(LLMError):
                runner.run()

    def test_system_prompt_uses_index_and_red_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            config = load_config("config.yaml")
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM([{"action": "finish", "params": {}}]),
            )
            prompt = runner._system_prompt()
            self.assertIn("可用文档索引", prompt)
            self.assertIn("红线（必须遵守", prompt)
            self.assertIn("read_document", prompt)
            self.assertIn("rules/03_迁移决策规范.md", prompt)
            self.assertNotIn("以下为项目约束上下文，必须遵守", prompt)

    def test_agentic_loop_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")

            decisions = [
                {"thought": "先扫描", "action": "scan_files", "params": {}},
                {"thought": "生成计划", "action": "propose_plan", "params": {}},
                {
                    "thought": "应用补丁",
                    "action": "apply_patch",
                    "params": {
                        "item": {
                            "id": "p1",
                            "file": "a.py",
                            "issue": "x",
                            "action": "copy",
                            "impact": "low",
                        }
                    },
                },
                {
                    "thought": "验证",
                    "action": "run_verifier",
                    "params": {"path": str(output / "a.py")},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]

            config = load_config("config.yaml")
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
                reviewer=lambda item, diff: {
                    "approved": True,
                    "issues": [],
                },
            )
            state = runner.run()

            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue((state.audit_dir() / "report.md").is_file())
            self.assertGreaterEqual(
                runner.dispatcher.call_counts()["scan_files"],
                1,
            )

    def test_agentic_semantic_edit_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "file": "a.py",
                "start_line": 1,
                "end_line": 1,
                "new_content": "x = 2\n",
                "reason": "semantic",
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {
                    "thought": "预览",
                    "action": "propose_edit",
                    "params": {"item": item},
                },
                {
                    "thought": "应用",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
                reviewer=lambda item, diff: {
                    "approved": True,
                    "issues": [],
                },
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 2\n",
            )

    def test_agentic_edit_requires_approval_for_medium(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "file": "a.py",
                "start_line": 1,
                "end_line": 1,
                "new_content": "x = 2\n",
                "reason": "semantic",
                "evidence": {"doc_id": "d1"},
                "impact": "medium",
            }
            decisions = [
                {
                    "thought": "预览",
                    "action": "propose_edit",
                    "params": {"item": item},
                },
                {
                    "thought": "应用",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
                reviewer=lambda item, diff: {
                    "approved": True,
                    "issues": [],
                },
            )
            with patch("builtins.input", return_value="y"):
                state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 2\n",
            )

    def test_agentic_edit_rejected_by_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "file": "a.py",
                "start_line": 1,
                "end_line": 1,
                "new_content": "x = 2\n",
                "reason": "semantic",
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {
                    "thought": "预览",
                    "action": "propose_edit",
                    "params": {"item": item},
                },
                {
                    "thought": "应用",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
                reviewer=lambda item, diff: {
                    "approved": False,
                    "issues": ["证据不相关"],
                },
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertFalse((output / "a.py").exists())
            self.assertTrue(
                any("评审未通过" in entry.message for entry in state.audit_entries)
            )

    def test_agentic_edit_requires_preview_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "file": "a.py",
                "start_line": 1,
                "end_line": 1,
                "new_content": "x = 2\n",
                "reason": "semantic",
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {
                    "thought": "应用",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
                reviewer=lambda item, diff: {
                    "approved": True,
                    "issues": [],
                },
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertFalse((output / "a.py").exists())
            self.assertTrue(
                any("缺少预览" in entry.message for entry in state.audit_entries)
            )


if __name__ == "__main__":
    unittest.main()
