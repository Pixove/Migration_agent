from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migration.scan_signals import scan_python_signals


class SignalScannerTests(unittest.TestCase):
    def test_detects_del_and_utcnow(self):
        source = (
            "class A:\n"
            "    def __del__(self):\n"
            "        pass\n"
            "now = datetime.utcnow()\n"
        )
        signals = scan_python_signals(source, "a.py")
        kinds = {signal["kind"] for signal in signals}
        self.assertIn("destructor", kinds)
        self.assertIn("deprecated_time", kinds)

    def test_clean_file_no_signals(self):
        source = "x = 1\ny = x + 1\n"
        self.assertEqual(scan_python_signals(source, "a.py"), [])

    def test_removed_modules(self):
        source = "import distutils\nfrom imp import load_source\n"
        signals = scan_python_signals(source, "a.py")
        self.assertEqual(len(signals), 2)

    def test_detects_rule_based_deprecated_api(self):
        source = (
            "import asyncio\n"
            "loop = asyncio.get_event_loop()\n"
        )
        signals = scan_python_signals(source, "a.py")
        self.assertTrue(
            any(
                signal["kind"] == "deprecated_api"
                and signal["api"] == "asyncio.get_event_loop"
                for signal in signals
            )
        )

    def test_detects_typing_alias_attribute(self):
        source = (
            "from typing import Dict\n"
            "x: Dict[str, int] = {}\n"
        )
        signals = scan_python_signals(source, "a.py")
        self.assertTrue(
            any(signal["api"] == "typing.Dict" for signal in signals)
        )

    def test_custom_rules_file_extends_scanner(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "rules.yaml"
            rules_path.write_text(
                "rules:\n"
                "  - id: legacy_call\n"
                "    kind: deprecated_api\n"
                "    type: call\n"
                "    name: mypkg.legacy_call\n"
                "    message: mypkg.legacy_call 已废弃\n",
                encoding="utf-8",
            )
            source = "import mypkg\nmypkg.legacy_call()\n"
            signals = scan_python_signals(
                source,
                "a.py",
                rules_path=rules_path,
            )
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["api"], "mypkg.legacy_call")


if __name__ == "__main__":
    unittest.main()
