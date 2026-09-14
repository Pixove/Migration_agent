from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.config import load_config


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
        config = load_config("config.yaml")
        self.assertFalse(config.verification.enabled)
        self.assertEqual(config.verification.import_modules, [])
        self.assertEqual(config.verification.commands, [])
        self.assertTrue(config.verification.fail_on_error)


if __name__ == "__main__":
    unittest.main()
