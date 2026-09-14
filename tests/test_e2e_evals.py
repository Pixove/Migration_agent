from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from evals.e2e_evals import infer_profile, run_e2e_evals


class FakeE2ELLM:
    def __init__(self, decisions):
        self.decisions = decisions
        self.index = 0

    def complete(self, messages, **kwargs):
        decision = self.decisions[
            min(self.index, len(self.decisions) - 1)
        ]
        self.index += 1
        return json.dumps(decision, ensure_ascii=False)


class E2EEvalTests(unittest.TestCase):
    def test_infer_profile(self):
        self.assertEqual(
            infer_profile("examples/langchain_legacy"),
            "langchain_community",
        )
        self.assertEqual(
            infer_profile("examples/semantic_big_demo"),
            "py3_upgrade",
        )

    def test_real_llm_entry_with_fake_model(self):
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
                "evidence": {"kind": "destructor"},
                "impact": "low",
            }
            llm = FakeE2ELLM(
                [
                    {"thought": "扫描", "action": "scan_files", "params": {}},
                    {
                        "thought": "编辑",
                        "action": "apply_edit",
                        "params": {"item": item},
                    },
                ]
            )
            config = load_config("config.yaml")
            config.retrieval.vector_enabled = False
            config.retrieval.rerank_enabled = False
            result = run_e2e_evals(
                source,
                config=config,
                output=output,
                profile="py3_upgrade",
                scope="syntax",
                llm=llm,
            )
            self.assertTrue(result["success"])
            self.assertEqual(result["applied_items"], 1)
            self.assertEqual(
                result["quality"]["unresolved_signal_count"],
                0,
            )
            self.assertIn(
                "close",
                (output / "a.py").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
