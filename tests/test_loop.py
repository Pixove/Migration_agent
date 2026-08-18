from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.guardrails import GuardrailError
from agent.llm import LLMError
from agent.loop import MigrationRunner
from agent.planning import build_fallback_plan, generate_llm_plan, refactor_ratio
from agent.state import Phase, PlanItem
from retrieval.knowledge_base import KnowledgeBase
from tools.scanner import FileInfo


class PlanningTests(unittest.TestCase):
    def test_fallback_plan_covers_all_files(self):
        plan = build_fallback_plan(["a.py", "b.py"])
        self.assertEqual([item.file for item in plan], ["a.py", "b.py"])
        self.assertTrue(all(item.action == "copy" for item in plan))

    def test_refactor_ratio_counts_transform_only(self):
        plan = [
            PlanItem(
                id="p1",
                file="a.py",
                issue="x",
                action="transform",
                impact="low",
            ),
            PlanItem(
                id="p2",
                file="b.py",
                issue="x",
                action="copy",
                impact="low",
            ),
        ]
        ratio = refactor_ratio(plan, {"a.py": 4, "b.py": 6})
        self.assertAlmostEqual(ratio, 0.4)


class FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    def complete(self, messages, **kwargs):
        import json

        return json.dumps(self.payload, ensure_ascii=False)

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
                        "evidence": {"doc_id": "d1"},
                    }
                ]
            }
        )
        plan = generate_llm_plan(client, ["a.py"], evidence_pool=["d1"])
        self.assertEqual(plan[0].file, "a.py")

    def test_plan_without_evidence_is_rejected(self):
        client = FakeLLM(
            {
                "items": [
                    {
                        "file": "a.py",
                        "issue": "x",
                        "action": "transform",
                        "impact": "low",
                    }
                ]
            }
        )
        with self.assertRaises(LLMError):
            generate_llm_plan(client, ["a.py"])

    def test_copy_without_evidence_is_accepted(self):
        client = FakeLLM(
            {
                "items": [
                    {
                        "file": "a.py",
                        "issue": "x",
                        "action": "copy",
                        "impact": "low",
                    }
                ]
            }
        )
        plan = generate_llm_plan(client, ["a.py"])
        self.assertEqual(plan[0].evidence, {})

    def test_evidence_must_reference_retrieval_pool(self):
        item = {
            "file": "a.py",
            "issue": "x",
            "action": "transform",
            "impact": "low",
            "evidence": {"doc_id": "d1"},
        }
        client = FakeLLM({"items": [item]})
        plan = generate_llm_plan(client, ["a.py"], evidence_pool=["d1"])
        self.assertEqual(plan[0].evidence, {"doc_id": "d1"})

        with self.assertRaises(LLMError):
            generate_llm_plan(client, ["a.py"], evidence_pool=["d2"])

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

    def test_full_flow_with_docs_and_kb(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            docs = Path(tmp) / "docs"
            source.mkdir()
            docs.mkdir()
            (source / "a.py").write_text("print('hello')\n", encoding="utf-8")
            (docs / "guide.txt").write_text(
                "migration best practice\n",
                encoding="utf-8",
            )

            config = load_config("config.yaml")
            config.retrieval.kb_dir = str(Path(tmp) / "kb")
            runner = MigrationRunner(
                config,
                source,
                output,
                docs=[docs],
                no_llm=True,
            )
            state = runner.run()

            self.assertEqual(state.phase, Phase.DONE)
            self.assertTrue((Path(tmp) / "kb" / "kb.json").is_file())

    def test_evidence_collection_uses_retriever(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            docs = Path(tmp) / "docs"
            source.mkdir()
            docs.mkdir()
            (source / "a.py").write_text("print('hello')\n", encoding="utf-8")
            (docs / "guide.txt").write_text(
                "print statement migration\n",
                encoding="utf-8",
            )

            config = load_config("config.yaml")
            config.retrieval.kb_dir = str(Path(tmp) / "kb")
            runner = MigrationRunner(config, source, output, docs=[docs], no_llm=True)
            kb = KnowledgeBase(config.retrieval.kb_dir)
            kb.import_source(docs)
            runner.retriever = kb.build_retriever(config.retrieval)
            runner.ctx.retriever = runner.retriever

            evidence, pool = runner._collect_evidence(["a.py"])
            self.assertTrue(evidence)
            self.assertTrue(pool)
            self.assertEqual(evidence[0]["file"], "a.py")
            self.assertLessEqual(len(evidence[0]["hits"]), 2)
            self.assertTrue(
                all(len(hit["snippet"]) <= 100 for hit in evidence[0]["hits"])
            )

    def test_refactor_threshold_blocks_without_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()

            config = load_config("config.yaml")
            plan = [
                PlanItem(
                    id="p1",
                    file="a.py",
                    issue="x",
                    action="transform",
                    impact="low",
                )
            ]
            files = [
                FileInfo("a.py", ".py", 40, 10),
                FileInfo("b.py", ".py", 10, 2),
            ]

            runner = MigrationRunner(
                config,
                source,
                output,
                no_llm=True,
                large_refactor_confirm=lambda ratio: False,
            )
            with self.assertRaises(GuardrailError):
                runner._enforce_refactor_threshold(plan, files)

            runner_ok = MigrationRunner(
                config,
                source,
                output,
                no_llm=True,
                large_refactor_confirm=lambda ratio: True,
            )
            ratio = runner_ok._enforce_refactor_threshold(plan, files)
            self.assertAlmostEqual(ratio, 10 / 12)


if __name__ == "__main__":
    unittest.main()
