from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import DEFAULT_ALLOWED_OUTPUT_ENTRIES, load_config


class ConfigFallbackTests(unittest.TestCase):
    def test_falls_back_to_example_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.example.yaml").write_text(
                "llm:\n"
                "  provider: ollama\n"
                "guardrails:\n"
                "  allowed_tools:\n"
                "    - scan_files\n",
                encoding="utf-8",
            )
            config = load_config(root / "config.yaml")
            self.assertEqual(config.llm.provider, "ollama")

    def test_default_refactor_ratio(self):
        config = load_config("config.yaml")
        self.assertEqual(config.guardrails.max_refactor_ratio, 0.3)

    def test_default_verification_config(self):
        config = load_config("config.example.yaml")
        self.assertFalse(config.verification.enabled)
        self.assertEqual(config.verification.target_python, "")
        self.assertEqual(config.verification.required_files, [])
        self.assertEqual(config.verification.required_packages, [])
        self.assertEqual(config.verification.import_modules, [])
        self.assertEqual(config.verification.commands, [])
        self.assertTrue(config.verification.fail_on_error)

    def test_default_allowed_output_entries(self):
        config = load_config("config.example.yaml")
        self.assertEqual(
            config.guardrails.allowed_output_entries,
            list(DEFAULT_ALLOWED_OUTPUT_ENTRIES),
        )

    def test_loads_target_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "guardrails:\n"
                "  allowed_tools:\n"
                "    - scan_files\n"
                "verification:\n"
                "  target_python: C:\\target\\.venv\\Scripts\\python.exe\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(
                config.verification.target_python,
                "C:\\target\\.venv\\Scripts\\python.exe",
            )


if __name__ == "__main__":
    unittest.main()
