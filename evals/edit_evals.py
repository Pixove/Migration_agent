from __future__ import annotations

import json
from pathlib import Path

GOLDEN_FILE = Path(__file__).parent / "golden" / "edit.json"


def load_golden(path: str | Path = GOLDEN_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_edit_proposal(case: dict, proposal: dict) -> dict:
    """判断一次语义编辑提案是否与 golden 期望一致。"""
    passed = (
        proposal.get("file") == case["file"]
        and proposal.get("start_line") == case["start_line"]
        and proposal.get("end_line") == case["end_line"]
        and proposal.get("new_content") == case["new_content"]
    )
    return {
        "name": case["name"],
        "passed": passed,
        "evidence_ok": bool(proposal.get("evidence")),
    }


def run_edit_evals(
    golden: dict | None = None,
    proposals: list[dict] | None = None,
) -> dict:
    """评估语义编辑提案质量；未提供提案时以 golden 自身为基线。"""
    golden = golden or load_golden()
    if proposals is None:
        proposals = list(golden["cases"])

    results = [
        evaluate_edit_proposal(case, proposal)
        for case, proposal in zip(golden["cases"], proposals)
    ]
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    return {
        "total": total,
        "passed": passed,
        "edit_accuracy": passed / total if total else 0.0,
        "cases": results,
    }
