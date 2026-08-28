from __future__ import annotations

import json
import unittest

from agent.review import review_edit


class FakeReviewLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete(self, messages, **kwargs):
        item = self.payload[min(self.calls, len(self.payload) - 1)]
        self.calls += 1
        if isinstance(item, str):
            return item
        return json.dumps(item, ensure_ascii=False)


class ReviewEditTests(unittest.TestCase):
    def test_approved_review(self):
        llm = FakeReviewLLM([{"approved": True, "issues": []}])
        result = review_edit(llm, {"file": "a.py"}, "--- a/a.py\n+++ b/a.py\n")
        self.assertTrue(result["approved"])
        self.assertEqual(result["issues"], [])

    def test_parse_failure_is_not_approved(self):
        llm = FakeReviewLLM(["not json at all"] * 3)
        result = review_edit(llm, {"file": "a.py"}, "diff")
        self.assertFalse(result["approved"])
        self.assertTrue(result["issues"])
        self.assertTrue(result["unavailable"])

    def test_retry_after_parse_failure(self):
        llm = FakeReviewLLM(
            ["bad json", {"approved": True, "issues": []}]
        )
        result = review_edit(llm, {"file": "a.py"}, "diff")
        self.assertTrue(result["approved"])
        self.assertEqual(llm.calls, 2)


if __name__ == "__main__":
    unittest.main()
