from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

import requests

from agent.config import LLMConfig
from agent.llm import OpenAICompatibleClient


def _ok_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": '{"ok": true}'}}]
    }
    return response


class OpenAICompatibleRetryTests(unittest.TestCase):
    def test_retries_connection_error_and_drops_json_mode(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        client = OpenAICompatibleClient(
            LLMConfig(
                openai_base_url="https://example.com/v1",
                openai_api_key_env="OPENAI_API_KEY",
            )
        )
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append(json)
            if len(calls) == 1:
                raise requests.exceptions.ConnectionError(
                    "remote closed connection"
                )
            return _ok_response()

        with patch("requests.post", side_effect=fake_post):
            raw = client.complete(
                [{"role": "user", "content": "x"}],
                json_mode=True,
            )
        self.assertEqual(len(calls), 2)
        self.assertNotIn("response_format", calls[1])


if __name__ == "__main__":
    unittest.main()
