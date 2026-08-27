from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
