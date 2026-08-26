from __future__ import annotations

import json
import unittest

from agent.review import review_edit


class FakeReviewLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, messages, **kwargs):
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False)


class ReviewEditTests(unittest.TestCase):
    def test_approved_review(self):
        llm = FakeReviewLLM({"approved": True, "issues": []})
        result = review_edit(llm, {"file": "a.py"}, "--- a/a.py\n+++ b/a.py\n")
        self.assertTrue(result["approved"])
        self.assertEqual(result["issues"], [])

    def test_parse_failure_is_not_approved(self):
        llm = FakeReviewLLM("not json at all")
        result = review_edit(llm, {"file": "a.py"}, "diff")
        self.assertFalse(result["approved"])
        self.assertTrue(result["issues"])


if __name__ == "__main__":
    unittest.main()
