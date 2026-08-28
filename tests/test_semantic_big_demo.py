from __future__ import annotations

import ast
import unittest
from pathlib import Path

from migration.scan_signals import scan_python_signals


class SemanticBigDemoTests(unittest.TestCase):
    def _py_files(self):
        source = Path("examples/semantic_big_demo")
        return [path for path in source.rglob("*.py") if path.is_file()]

    def test_total_lines_over_100(self):
        total = sum(
            len(path.read_text(encoding="utf-8-sig").splitlines())
            for path in self._py_files()
        )
        self.assertGreater(total, 100)

    def test_all_files_parse(self):
        for path in self._py_files():
            ast.parse(path.read_text(encoding="utf-8-sig"))

    def test_signals_detected(self):
        total = 0
        for path in self._py_files():
            text = path.read_text(encoding="utf-8-sig")
            total += len(
                scan_python_signals(text, path.relative_to("examples"))
            )
        self.assertGreaterEqual(total, 5)


if __name__ == "__main__":
    unittest.main()
