from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.agentic_evals import run_agentic_evals
from evals.edit_evals import run_edit_evals
from evals.migration_evals import run_migration_evals
from evals.retrieval_evals import run_retrieval_evals

REPORT_DIR = Path(__file__).parent / "reports"


def save_report(report: dict, output: str | Path | None = None) -> Path:
    """把评估报告写入 JSON 文件，返回保存路径。"""
    if output is None:
        target = (
            REPORT_DIR
            / f"eval_report_{datetime.now():%Y%m%d_%H%M%S}.json"
        )
    else:
        target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def extract_tool_trace(state: dict) -> list[str]:
    """从迁移 state.json 的审计记录提取真实工具调用序列。"""
    calls: list[str] = []
    for entry in state.get("audit_entries", []):
        if entry.get("tool") != "agentic":
            continue
        message = entry.get("message", "")
        if message.startswith("调用工具 "):
            calls.append(message[len("调用工具 ") :].split(" ")[0])
    return calls


def extract_edit_proposals(state: dict) -> list[dict]:
    """从迁移 state.json 提取已成功应用的语义编辑提案。"""
    proposals: list[dict] = []
    for entry in state.get("audit_entries", []):
        if entry.get("tool") != "agentic":
            continue
        if entry.get("message") != "调用工具 apply_edit":
            continue
        detail = entry.get("detail", {})
        if not detail.get("success"):
            continue
        item = detail.get("params", {}).get("item")
        if not isinstance(item, dict) or not item.get("file"):
            continue
        proposals.append(
            {
                "file": item.get("file"),
                "start_line": item.get("start_line"),
                "end_line": item.get("end_line"),
                "new_content": item.get("new_content")
                or item.get("replacement"),
                "evidence": item.get("evidence"),
            }
        )
    return proposals


def align_edit_proposals(
    golden: dict,
    proposals: list[dict],
) -> list[dict]:
    """按 golden 用例的文件名对齐真实提案，未找到的文件置空。"""
    by_name: dict[str, dict] = {}
    for proposal in proposals:
        name = Path(str(proposal.get("file", ""))).name
        by_name.setdefault(name, proposal)
    return [
        by_name.get(Path(str(case["file"])).name, {})
        for case in golden["cases"]
    ]


def _summary(report: dict) -> dict[str, Any]:
    """提取各模块关键指标，控制台只打印摘要。"""
    retrieval = report.get("retrieval", {})
    migration = report.get("migration", {})
    agentic = report.get("agentic", {}).get("result", {})
    edit = report.get("edit", {})
    retrieval_summary: dict[str, Any] = {
        "avg_recall": retrieval.get("avg_recall"),
        "avg_ndcg": retrieval.get("avg_ndcg"),
        "avg_mrr": retrieval.get("avg_mrr"),
    }
    profiles = retrieval.get("profiles")
    if profiles:
        retrieval_summary["profiles"] = {
            name: {
                "avg_recall": value.get("avg_recall"),
                "avg_ndcg": value.get("avg_ndcg"),
                "avg_mrr": value.get("avg_mrr"),
            }
            for name, value in profiles.items()
        }
    return {
        "retrieval": retrieval_summary,
        "migration": {
            "passed": migration.get("passed"),
            "total": migration.get("total"),
        },
        "agentic": {
            "tool_accuracy": agentic.get("tool_accuracy"),
            "sequence_match": agentic.get("sequence_match"),
            "violation_count": agentic.get("violation_count"),
        },
        "edit": {
            "passed": edit.get("passed"),
            "total": edit.get("total"),
            "edit_accuracy": edit.get("edit_accuracy"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="运行评估系统并将完整结果保存为 JSON 文件"
    )
    parser.add_argument(
        "--state",
        help="迁移输出的 state.json，用于真实 Agentic 轨迹与编辑提案评估",
    )
    parser.add_argument(
        "--edit-proposals",
        help="真实编辑提案 JSON 数组文件，按 golden cases 顺序",
    )
    parser.add_argument(
        "--output",
        help="评估报告保存路径，默认 evals/reports/ 下按时间命名",
    )
    args = parser.parse_args(argv)

    state: dict | None = None
    if args.state:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))

    edit_proposals: list[dict] | None = None
    if args.edit_proposals:
        edit_proposals = json.loads(
            Path(args.edit_proposals).read_text(encoding="utf-8")
        )

    from evals.edit_evals import load_golden as load_edit_golden

    if state:
        trace = extract_tool_trace(state)
        completed = state.get("phase") == "done"
        extracted_proposals = extract_edit_proposals(state)
        if edit_proposals is None and extracted_proposals:
            edit_proposals = align_edit_proposals(
                load_edit_golden(),
                extracted_proposals,
            )
    else:
        trace = None
        completed = True

    report = {
        "retrieval": run_retrieval_evals(),
        "migration": run_migration_evals(),
        "agentic": run_agentic_evals(
            trace=trace,
            completed=completed,
        ),
        "edit": run_edit_evals(proposals=edit_proposals),
    }
    path = save_report(report, args.output)
    print(f"评估报告已保存: {path}")
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
