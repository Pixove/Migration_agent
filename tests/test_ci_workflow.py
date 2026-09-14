from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CIWorkflowTests(unittest.TestCase):
    def test_ci_runs_tests_and_evals(self):
        workflow = Path(".github/workflows/ci.yml")
        self.assertTrue(workflow.is_file())
        data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        job = data["jobs"]["test"]
        runs = [
            step.get("run", "")
            for step in job["steps"]
            if "run" in step
        ]
        self.assertTrue(any("unittest" in command for command in runs))
        self.assertTrue(any("evals.run" in command for command in runs))
        self.assertIn("3.13", job["strategy"]["matrix"]["python-version"])


if __name__ == "__main__":
    unittest.main()
