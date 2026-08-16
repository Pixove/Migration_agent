from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.guardrails import GuardrailError, PathGuard
from agent.state import AuditWorkspace, MigrationState, PlanItem
from tools.patcher import apply_plan_item
from tools.reporter import write_report
from tools.scanner import scan_project
from tools.verifier import verify_file


def _load_guardrails_config():
    return load_config("config.yaml").guardrails


class ScannerTests(unittest.TestCase):
    def test_scan_filters_excluded_dirs_and_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            output = Path(tmp) / "out"
            root.mkdir()
            output.mkdir()

            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "c.pyc").write_bytes(b"")
            (root / "tool.exe").write_bytes(b"")

            files = scan_project(
                root,
                _load_guardrails_config(),
                PathGuard(root, output),
            )
            self.assertEqual(
                [file.relative_path for file in files],
                ["a.py", "sub/b.py"],
            )


class PatcherTests(unittest.TestCase):
    def test_copy_action_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            output = Path(tmp) / "out"
            root.mkdir()
            output.mkdir()
            (root / "a.py").write_text("print(1)\n", encoding="utf-8")

            item = PlanItem(
                id="p1",
                file="a.py",
                issue="skeleton",
                action="copy",
                impact="low",
            )
            result = apply_plan_item(item, PathGuard(root, output))

            self.assertTrue(result.success)
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "print(1)\n",
            )

    def test_path_escape_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            output = Path(tmp) / "out"
            root.mkdir()
            output.mkdir()

            item = PlanItem(
                id="p2",
                file="../evil.py",
                issue="skeleton",
                action="copy",
                impact="low",
            )
            with self.assertRaises(GuardrailError):
                apply_plan_item(item, PathGuard(root, output))


class VerifierTests(unittest.TestCase):
    def test_python_syntax_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = Path(tmp) / "ok.py"
            invalid = Path(tmp) / "bad.py"
            valid.write_text("x = 1\n", encoding="utf-8")
            invalid.write_text("def broken(:\n", encoding="utf-8")

            self.assertTrue(verify_file(valid).success)
            self.assertFalse(verify_file(invalid).success)

    def test_non_python_file_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = Path(tmp) / "notes.txt"
            text.write_text("hello\n", encoding="utf-8")
            self.assertTrue(verify_file(text).success)


class ReporterTests(unittest.TestCase):
    def test_write_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            output.mkdir()

            state = MigrationState(source, output)
            state.add_plan_item(
                PlanItem(
                    id="p1",
                    file="a.py",
                    issue="skeleton",
                    action="copy",
                    impact="low",
                    status="applied",
                )
            )
            workspace = AuditWorkspace(state)
            workspace.initialize()

            report = write_report(state, workspace)
            content = report.read_text(encoding="utf-8")
            self.assertIn("# 迁移报告", content)
            self.assertIn("a.py", content)


if __name__ == "__main__":
    unittest.main()
