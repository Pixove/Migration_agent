from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

from agent.config import VerificationConfig, load_config
from agent.guardrails import GuardrailError, PathGuard
from agent.state import AuditWorkspace, MigrationState, PlanItem
from tools.patcher import (
    apply_plan_item,
    capture_file_snapshot,
    restore_file_snapshot,
)
from tools.reporter import write_report
from tools.scanner import scan_project
from tools.verifier import run_behavior_verification, verify_file


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

    def test_bom_source_file_passes_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            output = Path(tmp) / "out"
            root.mkdir()
            output.mkdir()
            (root / "a.py").write_bytes(b"\xef\xbb\xbfprint('hello')\n")

            item = PlanItem(
                id="p3",
                file="a.py",
                issue="skeleton",
                action="copy",
                impact="low",
            )
            result = apply_plan_item(item, PathGuard(root, output))

            self.assertTrue(result.success)
            self.assertTrue(verify_file(result.output_path).success)


class FileSnapshotTests(unittest.TestCase):
    def test_restore_existing_file_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.py"
            target.write_bytes(b"x = 1\n")
            snapshot = capture_file_snapshot(target)
            target.write_bytes(b"def broken(:\n")

            action = restore_file_snapshot(snapshot)

            self.assertEqual(action, "restored")
            self.assertEqual(target.read_bytes(), b"x = 1\n")

    def test_restore_missing_file_removes_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.py"
            snapshot = capture_file_snapshot(target)
            target.write_bytes(b"new = True\n")

            action = restore_file_snapshot(snapshot)

            self.assertEqual(action, "removed")
            self.assertFalse(target.exists())


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

    def test_behavior_import_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = VerificationConfig(
                enabled=True,
                import_modules=["sys", "definitely_missing_module_xyz"],
            )
            result = run_behavior_verification(tmp, config)
            self.assertFalse(result.success)
            self.assertEqual(len(result.checks), 2)
            self.assertTrue(result.checks[0].ok)
            self.assertFalse(result.checks[1].ok)

    def test_behavior_command_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = VerificationConfig(
                enabled=True,
                commands=[f'"{sys.executable}" -c "import sys"'],
            )
            result = run_behavior_verification(tmp, config)
            self.assertTrue(result.success)

    def test_behavior_required_files_and_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("x = 1\n", encoding="utf-8")
            config = VerificationConfig(
                enabled=True,
                required_files=["app.py", "missing.py", "../outside.py"],
                required_packages=["PyYAML", "missing_package_xyz"],
            )
            result = run_behavior_verification(tmp, config)
            self.assertFalse(result.success)
            checks = {check.name: check.ok for check in result.checks}
            self.assertTrue(checks["file:app.py"])
            self.assertFalse(checks["file:missing.py"])
            self.assertFalse(checks["file:../outside.py"])
            self.assertTrue(checks["package:PyYAML"])
            self.assertFalse(checks["package:missing_package_xyz"])

    def test_behavior_rejects_bare_python_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = VerificationConfig(
                enabled=True,
                commands=[sys.executable],
            )
            result = run_behavior_verification(tmp, config)
            self.assertFalse(result.success)
            self.assertIn(
                "缺少 -c/-m 或脚本路径",
                result.checks[0].message,
            )


class ReporterTests(unittest.TestCase):
    def test_write_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            output.mkdir()

            state = MigrationState(source, output)
            state.profile = "py3_upgrade"
            state.scope = "deprecated_api"
            state.verification_checks = [
                {"name": "import:sys", "ok": True, "message": ""}
            ]
            state.add_plan_item(
                PlanItem(
                    id="p1",
                    file="a.py",
                    issue="skeleton",
                    action="copy",
                    impact="low",
                    status="applied",
                    evidence={
                        "signal": {
                            "rule_id": "datetime_utcnow",
                            "api": "datetime.utcnow",
                            "docs": "01_废弃API升级",
                        }
                    },
                )
            )
            state.unresolved_signals = [
                {
                    "file": "a.py",
                    "line": 3,
                    "message": "示例未修复信号",
                    "rule_id": "datetime_utcnow",
                    "api": "datetime.utcnow",
                    "docs": "01_废弃API升级",
                }
            ]
            workspace = AuditWorkspace(state)
            workspace.initialize()

            report = write_report(state, workspace)
            content = report.read_text(encoding="utf-8")
            self.assertIn("# 迁移报告", content)
            self.assertIn("a.py", content)
            self.assertIn("py3_upgrade", content)
            self.assertIn("datetime_utcnow", content)
            self.assertIn("01_废弃API升级", content)
            self.assertIn("行为验证", content)


if __name__ == "__main__":
    unittest.main()
