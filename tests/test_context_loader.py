from __future__ import annotations

import tempfile
import unittest

from agent.context_loader import build_planning_context, load_project_documents
from agent.planning import build_plan_messages


class ContextLoaderTests(unittest.TestCase):
    def test_loads_entry_rules_and_skills(self):
        documents = load_project_documents()
        self.assertIn("AGENTS.md", documents)
        self.assertIn("rules/03_迁移决策规范.md", documents)
        self.assertIn("skills/03_迁移规划.md", documents)

    def test_planning_context_contains_red_lines(self):
        context = build_planning_context()
        self.assertIn("Agent 行为入口", context)
        self.assertIn("大规模重构阈值", context)
        self.assertIn("混合检索", context)

    def test_missing_project_returns_empty_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(build_planning_context(tmp), "")

    def test_plan_messages_include_context(self):
        messages = build_plan_messages(["a.py"])
        self.assertIn("以下为项目约束上下文", messages[0]["content"])
        self.assertIn("a.py", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
