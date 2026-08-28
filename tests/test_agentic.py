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
        self._decision_index = 0

    def complete(self, messages, **kwargs):
        system = messages[0]["content"] if messages else ""
        if "迁移规划器" in system:
            payload = json.loads(messages[1]["content"])
            items = [
                {
                    "file": name,
                    "issue": "x",
                    "action": "copy",
                    "impact": "low",
                }
                for name in payload.get("files", [])
            ]
            return json.dumps({"items": items}, ensure_ascii=False)
        decision = self.decisions[
            min(self._decision_index, len(self.decisions) - 1)
        ]
        self._decision_index += 1
        return json.dumps(decision, ensure_ascii=False)


class FlakyAgentLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, messages, **kwargs):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


class LoopScanLLM:
    def complete(self, messages, **kwargs):
        return json.dumps(
            {"thought": "扫描", "action": "scan_files", "params": {}}
        )


class RecordingAgentLLM:
    def __init__(self, decisions):
        self.decisions = decisions
        self.histories = []
        self._index = 0

    def complete(self, messages, **kwargs):
        self.histories.append([dict(message) for message in messages])
        system = messages[0]["content"] if messages else ""
        if "迁移规划器" in system:
            payload = json.loads(messages[1]["content"])
            items = [
                {
                    "file": name,
                    "issue": "x",
                    "action": "copy",
                    "impact": "low",
                }
                for name in payload.get("files", [])
            ]
            return json.dumps({"items": items}, ensure_ascii=False)
        decision = self.decisions[min(self._index, len(self.decisions) - 1)]
        self._index += 1
        return json.dumps(decision, ensure_ascii=False)


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

    def test_agentic_read_only_loop_auto_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "应用",
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
                    "thought": "读源码",
                    "action": "read_source",
                    "params": {"path": "a.py"},
                },
                {
                    "thought": "读源码",
                    "action": "read_source",
                    "params": {"path": "a.py"},
                },
                {
                    "thought": "读源码",
                    "action": "read_source",
                    "params": {"path": "a.py"},
                },
                {
                    "thought": "读源码",
                    "action": "read_source",
                    "params": {"path": "a.py"},
                },
                {
                    "thought": "读源码",
                    "action": "read_source",
                    "params": {"path": "a.py"},
                },
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue(
                any("连续只读" in entry.message for entry in state.audit_entries)
            )

    def test_agentic_read_phase_not_cut_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "读源码",
                    "action": "read_source",
                    "params": {"path": "a.py"},
                },
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue(
                any("强制收尾" in entry.message for entry in state.audit_entries)
            )
            self.assertFalse(
                any("连续只读" in entry.message for entry in state.audit_entries)
            )

    def test_agentic_reports_unresolved_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text(
                "class A:\n"
                "    def __del__(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue(state.unresolved_signals)
            report = (state.audit_dir() / "report.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("未修复信号", report)

    def test_agentic_injects_signals_on_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text(
                "class A:\n"
                "    def __del__(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "应用",
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
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            llm = RecordingAgentLLM(decisions)
            runner = AgenticRunner(config, source, output, llm=llm)
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue(
                any(
                    "迁移信号清单" in message["content"]
                    for history in llm.histories
                    for message in history
                )
            )

    def test_agentic_flags_edit_with_remaining_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text(
                "class A:\n"
                "    def __del__(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            item = {
                "file": "a.py",
                "new_content": (
                    "class A:\n"
                    "    def close(self):\n"
                    "        pass\n"
                    "    def __del__(self):\n"
                    "        self.close()\n"
                ),
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "编辑",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            llm = RecordingAgentLLM(decisions)
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=llm,
                reviewer=lambda item, diff: {
                    "approved": True,
                    "issues": [],
                },
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue(
                any(
                    "信号仍存在" in message["content"]
                    for history in llm.histories
                    for message in history
                )
            )

    def test_agentic_apply_patch_requires_approval_for_medium(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            decisions = [
                {
                    "thought": "应用",
                    "action": "apply_patch",
                    "params": {
                        "item": {
                            "id": "p1",
                            "file": "a.py",
                            "issue": "x",
                            "action": "copy",
                            "impact": "medium",
                        }
                    },
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            with patch("builtins.input", return_value="n"):
                state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertFalse((output / "a.py").exists())
            self.assertTrue(
                any("用户拒绝应用" in entry.message for entry in state.audit_entries)
            )

    def test_agentic_auto_verify_rolls_back_invalid_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "file": "a.py",
                "new_content": "def broken(:\n",
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "编辑",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
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
                "x = 1\n",
            )
            self.assertTrue(
                any(
                    entry.message.startswith("应用后验证失败")
                    for entry in state.audit_entries
                )
            )
            self.assertTrue(
                any(item.status == "failed" for item in state.plan_items)
            )

    def test_agentic_review_unavailable_allows_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            item = {
                "file": "a.py",
                "new_content": "x = 2\n",
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "编辑",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
                reviewer=lambda item, diff: {
                    "approved": False,
                    "issues": ["评审不可用"],
                    "unavailable": True,
                },
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue(
                any("评审不可用" in entry.message for entry in state.audit_entries)
            )

    def test_agentic_skips_failed_read_document_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            decisions = [
                {
                    "thought": "读文档",
                    "action": "read_document",
                    "params": {"path": "docs/01_废弃API升级.md"},
                },
                {
                    "thought": "再读",
                    "action": "read_document",
                    "params": {"path": "docs/01_废弃API升级.md"},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertEqual(runner.dispatcher.call_counts()["read_document"], 1)

    def test_agentic_cannot_finish_with_unresolved_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text(
                "class A:\n"
                "    def __del__(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            item = {
                "file": "a.py",
                "new_content": (
                    "class A:\n"
                    "    def close(self):\n"
                    "        pass\n"
                ),
                "evidence": {"doc_id": "d1"},
                "impact": "low",
            }
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {"thought": "结束", "action": "finish", "params": {}},
                {
                    "thought": "修复",
                    "action": "apply_edit",
                    "params": {"item": item},
                },
                {"thought": "结束", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
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
                "class A:\n    def close(self):\n        pass\n",
            )
            self.assertEqual(state.unresolved_signals, [])

    def test_agentic_max_iterations_force_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=LoopScanLLM(),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue(
                any("强制收尾" in entry.message for entry in state.audit_entries)
            )

    def test_agentic_auto_finishes_after_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            (source / "b.py").write_text("y = 2\n", encoding="utf-8")
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {
                    "thought": "收尾",
                    "action": "write_report",
                    "params": {},
                },
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue((state.audit_dir() / "report.md").is_file())
            self.assertTrue(
                any("统一生成" in entry.message for entry in state.audit_entries)
            )
            report = (state.audit_dir() / "report.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("a.py", report)
            self.assertIn("b.py", report)

    def test_agentic_finalizes_unhandled_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("x = 1\n", encoding="utf-8")
            (source / "b.py").write_text("y = 2\n", encoding="utf-8")
            decisions = [
                {"thought": "扫描", "action": "scan_files", "params": {}},
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue((output / "b.py").is_file())
            self.assertEqual(len(state.plan_items), 2)

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
            self.assertIn("最多执行", prompt)
            self.assertIn("不要重复读取", prompt)
            self.assertIn("不能只叠加新写法", prompt)
            self.assertNotIn("以下为项目约束上下文，必须遵守", prompt)

    def test_agentic_skips_duplicate_read_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            decisions = [
                {
                    "thought": "读规则",
                    "action": "read_document",
                    "params": {"path": "rules/00_总则.md"},
                },
                {
                    "thought": "再读",
                    "action": "read_document",
                    "params": {"path": "rules/00_总则.md"},
                },
                {"thought": "完成", "action": "finish", "params": {}},
            ]
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM(decisions),
            )
            state = runner.run()
            self.assertEqual(state.phase.value, "done")
            self.assertEqual(runner.dispatcher.call_counts()["read_document"], 1)

    def test_history_trim_keeps_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            runner = AgenticRunner(
                config,
                source,
                output,
                llm=FakeAgentLLM([{"action": "finish", "params": {}}]),
            )
            messages = [{"role": "system", "content": "s"}] + [
                {"role": "user", "content": str(index)}
                for index in range(60)
            ]
            trimmed = runner._trim_history(messages)
            self.assertEqual(len(trimmed), 24)
            self.assertEqual(trimmed[0], messages[0])
            self.assertIn("当前运行摘要", trimmed[1]["content"])
            self.assertEqual(trimmed[-1], messages[-1])

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
            self.assertEqual(len(state.plan_items), 1)
            self.assertEqual(state.plan_items[0].status, "applied")

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
            self.assertEqual(state.plan_items[0].action, "edit")
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

    def test_agentic_edit_auto_generates_preview(self):
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
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "x = 2\n",
            )


if __name__ == "__main__":
    unittest.main()
