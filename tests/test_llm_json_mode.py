from __future__ import annotations

import unittest

from agent.config import LLMConfig
from agent.llm import LLMClient


class SpyClient(LLMClient):
    def __init__(self):
        super().__init__(LLMConfig())
        self.calls = []

    def ping(self) -> bool:
        return True

    def complete(
        self,
        messages,
        *,
        temperature=None,
        max_tokens=None,
        json_mode=False,
    ):
        self.calls.append(
            {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
            }
        )
        return '{"ok": true}'


class LLMJsonModeTests(unittest.TestCase):
    def test_complete_json_enables_json_mode(self):
        client = SpyClient()
        result = client.complete_json(
            [{"role": "user", "content": "x"}],
            max_tokens=64,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(client.calls[0]["json_mode"])
        self.assertEqual(client.calls[0]["max_tokens"], 64)


if __name__ == "__main__":
    unittest.main()
