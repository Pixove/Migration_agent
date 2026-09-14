from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.guardrails import GuardrailError, PathGuard


class OutputDirectoryGuardTests(unittest.TestCase):
    def _roots(self, tmp: str) -> tuple[Path, Path]:
        source = Path(tmp) / "src"
        output = Path(tmp) / "out"
        source.mkdir()
        return source, output

    def test_missing_output_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = self._roots(tmp)

            PathGuard(source, output)

    def test_empty_output_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = self._roots(tmp)
            output.mkdir()

            PathGuard(source, output)

    def test_only_allowlisted_runtime_directories_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = self._roots(tmp)
            output.mkdir()
            for name in (".venv", "venv", ".git", ".migration-agent"):
                (output / name).mkdir()

            PathGuard(source, output)

    def test_unexpected_output_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = self._roots(tmp)
            output.mkdir()
            (output / "legacy.py").write_text("print(1)\n", encoding="utf-8")

            with self.assertRaises(GuardrailError) as ctx:
                PathGuard(source, output)

            self.assertIn("legacy.py", str(ctx.exception))

    def test_custom_allowlist_can_enforce_empty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = self._roots(tmp)
            output.mkdir()
            (output / ".venv").mkdir()

            with self.assertRaises(GuardrailError):
                PathGuard(source, output, allowed_output_entries=[])


if __name__ == "__main__":
    unittest.main()
