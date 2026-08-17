from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.llm import LLMError
from agent.loop import MigrationRunner
from agent.planning import build_fallback_plan, generate_llm_plan
from agent.state import Phase


class PlanningTests(unittest.TestCase):
    def test_fallback_plan_covers_all_files(self):
        plan = build_fallback_plan(["a.py", "b.py"])
        self.assertEqual([item.file for item in plan], ["a.py", "b.py"])
        self.assertTrue(all(item.action == "copy" for item in plan))


class FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    def complete_json(self, messages, **kwargs):
        return self.payload


class LLMPlanTests(unittest.TestCase):
    def test_valid_plan_is_accepted(self):
        client = FakeLLM(
            {
                "items": [
                    {
                        "file": "a.py",
                        "issue": "语法过时",
                        "action": "copy",
                        "impact": "low",
                    }
                ]
            }
        )
        plan = generate_llm_plan(client, ["a.py"])
        self.assertEqual(plan[0].file, "a.py")

    def test_file_outside_scan_is_rejected(self):
        client = FakeLLM(
            {
                "items": [
                    {
                        "file": "missing.py",
                        "issue": "x",
                        "action": "copy",
                        "impact": "low",
                    }
                ]
            }
        )
        with self.assertRaises(LLMError):
            generate_llm_plan(client, ["a.py"])


class RunnerTests(unittest.TestCase):
    def test_full_flow_without_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            (source / "a.py").write_text("print('hello')\n", encoding="utf-8")
            (source / "notes.txt").write_text("best practice\n", encoding="utf-8")

            config = load_config("config.yaml")
            runner = MigrationRunner(config, source, output, no_llm=True)
            state = runner.run()

            self.assertEqual(state.phase, Phase.DONE)
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue((output / "notes.txt").is_file())
            self.assertTrue((state.audit_dir() / "state.json").is_file())
            self.assertTrue((state.audit_dir() / "report.md").is_file())
            self.assertTrue(
                all(item.status == "applied" for item in state.plan_items)
            )
            counts = runner.dispatcher.call_counts()
            self.assertEqual(counts["scan_files"], 1)
            self.assertEqual(counts["propose_plan"], 1)
            self.assertEqual(counts["write_report"], 1)
            self.assertEqual(counts["apply_patch"], 2)
            self.assertEqual(counts["run_verifier"], 2)


if __name__ == "__main__":
    unittest.main()
