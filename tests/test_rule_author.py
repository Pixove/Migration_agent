from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from migration.rule_author import (
    extract_rule_candidates,
    load_document_text,
    validate_candidate_rules,
    write_candidate_files,
)
from migration.scan_signals import parse_api_rules


class FakeRuleAuthorLLM:
    def __init__(self, rules):
        self.rules = rules

    def complete(self, messages, **kwargs):
        return json.dumps({"rules": self.rules}, ensure_ascii=False)


class RuleAuthorTests(unittest.TestCase):
    def _candidate(self):
        return {
            "id": "legacy_import",
            "kind": "deprecated_api",
            "type": "from_import",
            "module": "oldpkg",
            "name": "OldThing",
            "replacement": "from newpkg import NewThing",
            "message": "OldThing 已迁移到 NewThing",
            "docs": "upgrade_guide",
            "severity": "medium",
        }

    def test_extract_and_write_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "guide.md"
            docs.write_text(
                "from oldpkg import OldThing\n"
                "请替换为 from newpkg import NewThing\n",
                encoding="utf-8",
            )
            text, loaded = load_document_text([docs])
            candidates = extract_rule_candidates(
                text,
                FakeRuleAuthorLLM([self._candidate()]),
            )
            self.assertEqual(candidates, [self._candidate()])
            self.assertEqual(len(loaded), 1)

            report = validate_candidate_rules(
                candidates,
                existing_rules=[],
            )
            self.assertEqual(report.errors, [])
            output = Path(tmp) / "candidates.yaml"
            yaml_path, review_path = write_candidate_files(
                output,
                candidates,
                report,
                source_paths=[docs],
            )
            self.assertTrue(yaml_path.is_file())
            self.assertTrue(review_path.is_file())
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            self.assertEqual(data["rules"][0]["id"], "legacy_import")

    def test_conflicting_candidate_reports_error(self):
        existing_rule = {
            "id": "existing_rule",
            "kind": "deprecated_api",
            "type": "from_import",
            "module": "oldpkg",
            "name": "OldThing",
            "replacement": "from newpkg import OtherThing",
            "message": "已有规则",
        }
        existing = list(
            parse_api_rules([existing_rule], source="<existing>")
        )
        report = validate_candidate_rules(
            [self._candidate()],
            existing_rules=existing,
        )
        self.assertTrue(report.errors)
        self.assertTrue(
            any("replacement 不同" in error for error in report.errors)
        )

    def test_invalid_candidate_returns_error(self):
        report = validate_candidate_rules(
            [{"id": "broken", "type": "call"}],
            existing_rules=[],
        )
        self.assertTrue(report.errors)
        self.assertEqual(report.rules, [])


if __name__ == "__main__":
    unittest.main()
