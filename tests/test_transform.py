from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from agent.config import load_config
from agent.dispatcher import ToolDispatcher
from agent.guardrails import PathGuard, ToolRegistry
from agent.tooling import ToolContext, register_tools
from migration.py2to3 import transform_python2_to_3


class Py2To3TransformTests(unittest.TestCase):
    def test_print_statement(self):
        self.assertEqual(
            transform_python2_to_3("print 'hello'\n"),
            "print('hello')\n",
        )

    def test_print_with_comment(self):
        self.assertEqual(
            transform_python2_to_3("print 'hello' # note\n"),
            "print('hello') # note\n",
        )

    def test_print_function_unchanged(self):
        self.assertEqual(
            transform_python2_to_3("print('hello')\n"),
            "print('hello')\n",
        )

    def test_except_clause(self):
        self.assertEqual(
            transform_python2_to_3("except Exception, e:\n"),
            "except Exception as e:\n",
        )

    def test_builtin_rewrites(self):
        source = (
            "for i in xrange(10):\n"
            "name = raw_input('name: ')\n"
            "value = long(3)\n"
            "s = basestring\n"
        )
        expected = (
            "for i in range(10):\n"
            "name = input('name: ')\n"
            "value = int(3)\n"
            "s = str\n"
        )
        self.assertEqual(transform_python2_to_3(source), expected)

    def test_unicode_literal(self):
        self.assertEqual(
            transform_python2_to_3("s = u'hello'\n"),
            "s = 'hello'\n",
        )


class TransformIntegrationTests(unittest.TestCase):
    def test_apply_patch_uses_transform_for_transform_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            output.mkdir()
            (source / "a.py").write_text("print 'hello'\n", encoding="utf-8")

            config = load_config("config.yaml")
            guard = PathGuard(source, output)
            ctx = ToolContext(config=config, guard=guard)
            dispatcher = ToolDispatcher(
                ToolRegistry(config.guardrails.allowed_tools)
            )
            register_tools(dispatcher, ctx)

            result = dispatcher.call(
                "apply_patch",
                item={
                    "id": "p1",
                    "file": "a.py",
                    "issue": "python2 print",
                    "action": "transform",
                    "impact": "low",
                    "evidence": {"doc_id": "d1"},
                },
            )
            self.assertTrue(result.success)
            self.assertEqual(
                (output / "a.py").read_text(encoding="utf-8"),
                "print('hello')\n",
            )

    def test_legacy_demo_transforms_to_valid_python3(self):
        source = Path(
            "examples/legacy_demo/python2_demo.py"
        ).read_text(encoding="utf-8-sig")
        migrated = transform_python2_to_3(source)
        ast.parse(migrated)

    def test_all_demo_py_files_transform_to_valid_python3(self):
        source = Path("examples/legacy_demo")
        py_files = [path for path in source.rglob("*.py") if path.is_file()]
        self.assertGreater(len(py_files), 5)
        for file in py_files:
            text = file.read_text(encoding="utf-8-sig")
            migrated = transform_python2_to_3(text)
            ast.parse(migrated)


if __name__ == "__main__":
    unittest.main()
