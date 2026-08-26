from __future__ import annotations

import unittest

from agent.config import load_config
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


if __name__ == "__main__":
    unittest.main()
