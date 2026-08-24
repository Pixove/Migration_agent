from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.chat import ChatSession, _keyword_intent
from agent.config import load_config


class KeywordIntentTests(unittest.TestCase):
    def test_py3_upgrade_goal(self):
        intent = _keyword_intent("把 Python 3.8 升级到 3.13")
        self.assertEqual(intent["profile"], "py3_upgrade")

    def test_unknown_goal(self):
        intent = _keyword_intent("把 Django 升级到最新")
        self.assertEqual(intent["profile"], "unknown")


class FakeIntentLLM:
    def complete(self, messages, **kwargs):
        return json.dumps(
            {
                "profile": "py3_upgrade",
                "scope": "deprecated_api",
                "needs_more_info": "",
            }
        )


class ChatSessionTests(unittest.TestCase):
    def test_run_with_keyword_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            config = load_config("config.yaml")
            session = ChatSession(config, llm=None)
            answers = [
                "把 Python 3.8 升级到 3.13",
                str(source),
                str(output),
                "y",
            ]
            with patch("builtins.input", side_effect=answers):
                result = session.run()
            self.assertEqual(result.profile, "py3_upgrade")
            self.assertEqual(result.scope, "syntax")
            self.assertEqual(result.source, str(source))
            self.assertEqual(result.output, str(output))

    def test_reask_after_irrelevant_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            output = Path(tmp) / "out"
            source.mkdir()
            config = load_config("config.yaml")
            session = ChatSession(config, llm=None)
            answers = [
                "帮我迁移数据库到MongoDB",
                "把 Python 3.8 升级到 3.13",
                str(source),
                str(output),
                "y",
            ]
            with patch("builtins.input", side_effect=answers) as mocked:
                result = session.run()
            self.assertEqual(result.profile, "py3_upgrade")
            self.assertEqual(mocked.call_count, 5)

    def test_three_failures_abort(self):
        config = load_config("config.yaml")
        session = ChatSession(config, llm=None)
        with patch("builtins.input", side_effect=["迁移数据库"] * 3):
            with self.assertRaises(RuntimeError):
                session.run()

    def test_llm_intent_extraction(self):
        config = load_config("config.yaml")
        session = ChatSession(config, llm=FakeIntentLLM())
        intent = session._extract_intent("随便描述")
        self.assertEqual(intent["profile"], "py3_upgrade")
        self.assertEqual(intent["scope"], "deprecated_api")


if __name__ == "__main__":
    unittest.main()
