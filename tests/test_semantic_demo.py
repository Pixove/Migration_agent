from __future__ import annotations

import ast
import unittest
from pathlib import Path


class SemanticDemoTests(unittest.TestCase):
    def test_all_files_parse(self):
        source = Path("examples/semantic_demo")
        py_files = [path for path in source.rglob("*.py") if path.is_file()]
        self.assertGreater(len(py_files), 3)
        for file in py_files:
            ast.parse(file.read_text(encoding="utf-8-sig"))

    def test_demo_contains_semantic_issues(self):
        source = Path("examples/semantic_demo")
        session = (source / "utils" / "session.py").read_text(encoding="utf-8-sig")
        timeutil = (source / "utils" / "timeutil.py").read_text(encoding="utf-8-sig")
        counter = (source / "services" / "counter.py").read_text(encoding="utf-8-sig")
        self.assertIn("__del__", session)
        self.assertIn("utcnow", timeutil)
        self.assertIn("self.value += 1", counter)


if __name__ == "__main__":
    unittest.main()
