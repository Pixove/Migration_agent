from __future__ import annotations

import unittest

from agent.config import load_config
from evals.agentic_evals import evaluate_agentic_run, run_agentic_evals
from evals.edit_evals import (
    evaluate_edit_proposal,
    load_golden as load_edit_golden,
    run_edit_evals,
)
from evals.migration_evals import run_migration_evals
from evals.retrieval_evals import run_retrieval_evals


class MigrationEvalTests(unittest.TestCase):
    def test_all_golden_cases_pass(self):
        report = run_migration_evals()
        self.assertEqual(report["passed"], report["total"])


class RetrievalEvalTests(unittest.TestCase):
    def test_bm25_recall_on_golden_queries(self):
        config = load_config("config.yaml")
        config.retrieval.vector_enabled = False
        config.retrieval.rerank_enabled = False
        report = run_retrieval_evals(config=config)
        self.assertEqual(report["avg_recall"], 1.0)


class AgenticEvalTests(unittest.TestCase):
    def test_perfect_trace_scores(self):
        report = run_agentic_evals()
        self.assertEqual(report["result"]["tool_accuracy"], 1.0)
        self.assertTrue(report["result"]["sequence_match"])
        self.assertTrue(report["result"]["completion"])

    def test_violation_detected(self):
        config = load_config("config.yaml")
        result = evaluate_agentic_run(
            ["rm_all"],
            ["scan_files"],
            completed=False,
            allowed_tools=set(config.guardrails.allowed_tools),
        )
        self.assertEqual(result["violation_count"], 1)
        self.assertFalse(result["completion"])


class EditEvalTests(unittest.TestCase):
    def test_golden_baseline_passes(self):
        report = run_edit_evals()
        self.assertEqual(report["passed"], report["total"])

    def test_wrong_edit_fails(self):
        golden = load_edit_golden()
        proposal = {
            "file": golden["cases"][0]["file"],
            "start_line": 99,
            "end_line": 99,
            "new_content": "wrong",
            "evidence": {"doc_id": "d1"},
        }
        result = evaluate_edit_proposal(golden["cases"][0], proposal)
        self.assertFalse(result["passed"])
        self.assertTrue(result["evidence_ok"])


if __name__ == "__main__":
    unittest.main()
