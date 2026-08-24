from __future__ import annotations

import unittest

from migration.profiles.py3_upgrade.transform import transform_py3_upgrade


class Py3UpgradeTransformTests(unittest.TestCase):
    def test_typing_alias_rewritten(self):
        source = (
            "from typing import Dict, List\n"
            "x: Dict[str, int] = {}\n"
            "y: List[int] = []\n"
        )
        result = transform_py3_upgrade(source)
        self.assertIn("x: dict[str, int]", result)
        self.assertIn("y: list[int]", result)

    def test_typing_attribute_rewritten(self):
        source = "import typing\nx: typing.Dict[str, int] = {}\n"
        result = transform_py3_upgrade(source)
        self.assertIn("x: dict[str, int]", result)

    def test_utcnow_gets_todo_comment(self):
        source = (
            "from datetime import datetime\n"
            "now = datetime.utcnow()\n"
        )
        result = transform_py3_upgrade(source)
        self.assertIn("TODO(migration): datetime.utcnow", result)

    def test_distutils_import_gets_todo(self):
        source = "from distutils.core import setup\n"
        result = transform_py3_upgrade(source)
        self.assertIn("TODO(migration): distutils", result)

    def test_syntax_error_returns_unchanged(self):
        source = "print 'python2 syntax'\n"
        self.assertEqual(transform_py3_upgrade(source), source)


if __name__ == "__main__":
    unittest.main()
