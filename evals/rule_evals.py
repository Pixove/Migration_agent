from __future__ import annotations

import json
from pathlib import Path

from migration.scan_signals import scan_python_signals

GOLDEN_FILE = Path(__file__).parent / "golden" / "rules.json"


def load_golden(path: str | Path = GOLDEN_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_rule_evals(golden: dict | None = None) -> dict:
    """评估规则表对示例项目的 API 覆盖度。"""
    golden = golden or load_golden()
    cases: list[dict] = []

    for item in golden.get("cases", []):
        root = Path(item["path"])
        detected: set[str] = set()
        files = (
            [root]
            if root.is_file()
            else sorted(root.rglob("*.py"))
        )
        for file in files:
            if not file.is_file():
                continue
            signals = scan_python_signals(
                file.read_text(encoding="utf-8-sig", errors="ignore"),
                file.as_posix(),
            )
            detected.update(
                str(signal.get("api", ""))
                for signal in signals
                if signal.get("api")
            )

        expected = set(item.get("expected", []))
        matched = expected.intersection(detected)
        missing = sorted(expected - detected)
        extra = sorted(detected - expected)
        recall = len(matched) / len(expected) if expected else 1.0
        cases.append(
            {
                "name": item.get("name", ""),
                "path": str(root),
                "expected_count": len(expected),
                "detected_count": len(detected),
                "matched_count": len(matched),
                "missing": missing,
                "extra": extra,
                "recall": recall,
            }
        )

    total = len(cases)
    average = (
        sum(case["recall"] for case in cases) / total if total else 1.0
    )
    return {
        "total": total,
        "avg_recall": average,
        "cases": cases,
    }
