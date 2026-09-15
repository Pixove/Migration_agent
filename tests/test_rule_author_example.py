from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migration.rule_author import (
    build_profile_candidate,
    evaluate_candidate_coverage,
    validate_candidate_rules,
    write_candidate_files,
)
from migration.registry import parse_profile_definition

DEMO_ROOT = Path("examples/rule_author_demo")


class RuleAuthorExampleTests(unittest.TestCase):
    def _candidate_rules(self) -> list[dict]:
        return [
            {
                "id": "samplelib_old_model",
                "kind": "deprecated_api",
                "type": "from_import",
                "module": "samplelib.old",
                "name": "OldModel",
                "replacement": "from samplelib.models import Model",
                "message": "OldModel 已迁移到 Model",
                "docs": "samplelib_upgrade",
                "severity": "medium",
            },
            {
                "id": "samplelib_legacy_client",
                "kind": "deprecated_api",
                "type": "call",
                "name": "samplelib.client.LegacyClient",
                "replacement": "samplelib.client.Client",
                "message": "LegacyClient 已改名为 Client",
                "docs": "samplelib_upgrade",
                "severity": "medium",
            },
            {
                "id": "samplelib_load_config",
                "kind": "deprecated_api",
                "type": "call",
                "name": "samplelib.utils.load_config",
                "replacement": "samplelib.config.load_config",
                "message": "load_config 已迁移到 samplelib.config",
                "docs": "samplelib_upgrade",
                "severity": "medium",
            },
        ]

    def test_demo_contains_all_documented_apis(self):
        guide = (
            DEMO_ROOT / "knowledge" / "samplelib_upgrade.md"
        ).read_text(encoding="utf-8")
        legacy = (DEMO_ROOT / "legacy_app.py").read_text(encoding="utf-8")
        for api in (
            "samplelib.old.OldModel",
            "samplelib.client.LegacyClient",
            "samplelib.utils.load_config",
        ):
            self.assertIn(api, guide)
            self.assertIn(api.split(".")[-1], legacy)

    def test_demo_candidates_cover_legacy_app(self):
        guide = DEMO_ROOT / "knowledge" / "samplelib_upgrade.md"
        legacy = DEMO_ROOT / "legacy_app.py"
        candidates = self._candidate_rules()
        report = validate_candidate_rules(
            candidates,
            existing_rules=[],
        )
        self.assertEqual(report.errors, [])

        with tempfile.TemporaryDirectory() as tmp:
            rules_path, _ = write_candidate_files(
                Path(tmp) / "samplelib_upgrade.yaml",
                candidates,
                report,
                source_paths=[guide],
            )
            coverage = evaluate_candidate_coverage(rules_path, legacy)

        self.assertEqual(coverage["candidate_count"], 3)
        self.assertEqual(coverage["matched_count"], 3)
        self.assertEqual(coverage["missing"], [])

    def test_demo_profile_candidate_is_valid(self):
        guide = DEMO_ROOT / "knowledge" / "samplelib_upgrade.md"
        profile = build_profile_candidate(
            "samplelib_upgrade",
            self._candidate_rules(),
            [guide],
        )
        parsed = parse_profile_definition(profile, source="<demo>")
        self.assertEqual(parsed.name, "samplelib_upgrade")
        self.assertEqual(parsed.default_scope, "deprecated_api")
        self.assertEqual(
            parsed.rules,
            ["migration/rules/profiles/samplelib_upgrade.yaml"],
        )


if __name__ == "__main__":
    unittest.main()
