from __future__ import annotations

import json
from pathlib import Path

from agent.config import AppConfig, load_config
from agent.state import MigrationState

GOLDEN_FILE = Path(__file__).parent / "golden" / "agentic.json"


def load_golden(path: str | Path = GOLDEN_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_agentic_run(
    tool_calls: list[str],
    expected_sequence: list[str],
    completed: bool,
    allowed_tools: set[str],
) -> dict:
    """评估一次 Agentic 执行的工具序列质量。"""
    violations = [
        call for call in tool_calls if call not in allowed_tools
    ]
    matched = sum(
        1
        for call, expected in zip(tool_calls, expected_sequence)
        if call == expected
    )
    accuracy = (
        matched / len(expected_sequence)
        if expected_sequence
        else 0.0
    )
    return {
        "tool_calls": tool_calls,
        "tool_accuracy": accuracy,
        "sequence_match": tool_calls == expected_sequence,
        "completion": completed,
        "violation_count": len(violations),
        "step_count": len(tool_calls),
    }


def run_agentic_evals(
    golden: dict | None = None,
    trace: list[str] | None = None,
    completed: bool = True,
    config: AppConfig | None = None,
) -> dict:
    """运行 Agentic 编排评估；未提供 trace 时使用 golden 期望序列。"""
    golden = golden or load_golden()
    config = config or load_config("config.yaml")
    allowed = set(config.guardrails.allowed_tools)
    if trace is None:
        trace = list(golden["expected_sequence"])
    return {
        "scenario": golden["scenario"],
        "result": evaluate_agentic_run(
            trace,
            golden["expected_sequence"],
            completed,
            allowed,
        ),
    }


def extract_tool_trace(state: MigrationState) -> list[str]:
    """从任务审计记录中提取实际工具调用顺序。"""
    calls: list[str] = []
    for entry in state.audit_entries:
        if entry.phase == "agentic" and entry.message.startswith("调用工具 "):
            name = entry.message[len("调用工具 ") :].split(" ")[0].strip()
            calls.append(name)
    return calls
