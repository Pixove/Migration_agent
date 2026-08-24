from __future__ import annotations

import ast
import unittest
from pathlib import Path

from migration.profiles.py3_upgrade.transform import transform_py3_upgrade


class Py38DemoTests(unittest.TestCase):
    def test_all_files_transform_to_valid_python3(self):
        source = Path("examples/py38_demo")
        py_files = [path for path in source.rglob("*.py") if path.is_file()]
        self.assertGreater(len(py_files), 5)
        for file in py_files:
            text = file.read_text(encoding="utf-8-sig")
            migrated = transform_py3_upgrade(text)
            ast.parse(migrated)

    def test_typing_alias_and_utcnow_transformed(self):
        user_source = Path(
            "examples/py38_demo/models/user.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(
            "scores: dict[str, int]",
            transform_py3_upgrade(user_source),
        )

        time_source = Path(
            "examples/py38_demo/utils/timeutil.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(
            "TODO(migration): datetime.utcnow",
            transform_py3_upgrade(time_source),
        )


if __name__ == "__main__":
    unittest.main()
