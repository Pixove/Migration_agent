from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.agentic import AgenticRunner
from agent.config import load_config


class FakeAgentLLM:
    def __init__(self, decisions):
        self.decisions = decisions
        self.calls = 0

    def complete(self, messages, **kwargs):
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return json.dumps(decision, ensure_ascii=False)


class AgenticRunnerTests(unittest.TestCase):
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
            )
            state = runner.run()

            self.assertEqual(state.phase.value, "done")
            self.assertTrue((output / "a.py").is_file())
            self.assertTrue((state.audit_dir() / "report.md").is_file())
            self.assertGreaterEqual(
                runner.dispatcher.call_counts()["scan_files"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
