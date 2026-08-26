from __future__ import annotations

import json
from pathlib import Path

from migration.registry import load_profile

GOLDEN_FILE = Path(__file__).parent / "golden" / "migration.json"


def load_golden(path: str | Path = GOLDEN_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_migration_evals(golden: dict | None = None) -> dict:
    """对 golden 迁移对执行当前档案的 transform 并统计通过率。"""
    golden = golden or load_golden()
    cases = []
    for case in golden["cases"]:
        profile = load_profile(case["profile"])
        output = profile.transform(case["source"], None)
        if "expected" in case:
            passed = output == case["expected"]
            reason = (
                ""
                if passed
                else f"期望 {case['expected']!r}，实际 {output!r}"
            )
        elif "contains" in case:
            passed = case["contains"] in output
            reason = "" if passed else f"缺少 {case['contains']!r}"
        else:
            passed = False
            reason = "用例缺少 expected/contains"
        cases.append(
            {
                "name": case["name"],
                "profile": case["profile"],
                "passed": passed,
                "reason": reason,
            }
        )

    return {
        "total": len(cases),
        "passed": sum(1 for case in cases if case["passed"]),
        "cases": cases,
    }
