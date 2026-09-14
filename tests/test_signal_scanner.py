from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migration.registry import load_profile
from migration.scan_signals import (
    rules_paths_for_profile,
    scan_python_signals,
)


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
                "    replacement: mypkg.new_call\n"
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

    def test_from_import_rule_matches_module_and_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "rules.yaml"
            rules_path.write_text(
                "rules:\n"
                "  - id: langchain_chroma_import\n"
                "    kind: deprecated_api\n"
                "    type: from_import\n"
                "    module: langchain_community.vectorstores\n"
                "    name: Chroma\n"
                "    replacement: from langchain_chroma import Chroma\n"
                "    message: Chroma 已迁移到 langchain_chroma\n"
                "    docs: langchain_community_upgrade\n",
                encoding="utf-8",
            )
            source = "from langchain_community.vectorstores import Chroma\n"
            signals = scan_python_signals(
                source,
                "app.py",
                rules_path=rules_path,
            )
            self.assertEqual(len(signals), 1)
            self.assertEqual(
                signals[0]["api"],
                "langchain_community.vectorstores.Chroma",
            )

    def test_rule_directory_merges_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            (rules_dir / "a.yaml").write_text(
                "rules:\n"
                "  - id: module_a\n"
                "    kind: removed_module\n"
                "    type: module\n"
                "    name: legacy_a\n"
                "    message: legacy_a 已移除\n",
                encoding="utf-8",
            )
            (rules_dir / "b.yaml").write_text(
                "rules:\n"
                "  - id: symbol_b\n"
                "    kind: deprecated_api\n"
                "    type: from_import\n"
                "    module: legacy_b\n"
                "    name: OldThing\n"
                "    replacement: NewThing\n"
                "    message: OldThing 已废弃\n",
                encoding="utf-8",
            )
            source = "import legacy_a\nfrom legacy_b import OldThing\n"
            signals = scan_python_signals(
                source,
                "app.py",
                rules_path=rules_dir,
            )
            self.assertEqual(len(signals), 2)
            self.assertEqual(
                {signal["api"] for signal in signals},
                {"legacy_a", "legacy_b.OldThing"},
            )

    def test_profile_rules_detect_langchain_community_import(self):
        source = "from langchain_community.vectorstores import Chroma\n"
        rules_path = list(
            rules_paths_for_profile(
                load_profile("langchain_community").rules
            )
        )
        signals = scan_python_signals(
            source,
            "app.py",
            rules_path=rules_path,
        )
        self.assertTrue(
            any(
                signal["api"] == "langchain_community.vectorstores.Chroma"
                for signal in signals
            )
        )
        self.assertEqual(
            scan_python_signals(source, "app.py"),
            [],
        )

    def test_invalid_rule_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "rules.yaml"
            rules_path.write_text(
                "rules:\n"
                "  - id: broken\n"
                "    kind: deprecated_api\n"
                "    type: unknown_type\n"
                "    name: old_api\n"
                "    replacement: new_api\n"
                "    message: old_api 已废弃\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                scan_python_signals(
                    "old_api()\n",
                    "a.py",
                    rules_path=rules_path,
                )


if __name__ == "__main__":
    unittest.main()
