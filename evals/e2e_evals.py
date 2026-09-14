from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Callable

from agent.agentic import AgenticRunner
from agent.config import AppConfig, load_config
from agent.llm import LLMClient
from evals.quality_evals import run_quality_evals

DEFAULT_E2E_SOURCE = Path("examples/semantic_big_demo")


def infer_profile(source: str | Path) -> str:
    """根据示例目录名推断迁移档案。"""
    name = Path(source).name.lower()
    if "langchain" in name:
        return "langchain_community"
    return "py3_upgrade"


def run_e2e_evals(
    source: str | Path | None = None,
    *,
    config: AppConfig | None = None,
    output: str | Path | None = None,
    profile: str | None = None,
    scope: str | None = None,
    docs: list[str | Path] | None = None,
    llm: LLMClient | None = None,
    reviewer: Callable[[dict, str], dict] | None = None,
    auto_approve: bool = True,
) -> dict:
    """运行一次真实 Agentic 迁移并评估输出质量。"""
    source_path = Path(source or DEFAULT_E2E_SOURCE)
    config = config or load_config("config.yaml")
    config.migration.profile = profile or infer_profile(source_path)
    if scope:
        config.migration.scope = scope

    output_path = (
        Path(output)
        if output
        else Path(tempfile.mkdtemp(prefix="migration-e2e-"))
    )
    started = time.perf_counter()
    error: str | None = None
    state = None

    if not source_path.is_dir():
        error = f"示例项目不存在或不是目录: {source_path}"
    else:
        try:
            runner = AgenticRunner(
                config,
                source_path,
                output_path,
                docs=docs or [],
                auto_approve=auto_approve,
                llm=llm,
                reviewer=reviewer,
            )
            state = runner.run()
        except Exception as exc:
            error = str(exc)

    quality = run_quality_evals(output_path, config)
    duration = time.perf_counter() - started
    phase = state.phase.value if state is not None else "failed"
    plan_items = state.plan_items if state is not None else []
    applied = sum(1 for item in plan_items if item.status == "applied")
    failed = sum(1 for item in plan_items if item.status == "failed")
    success = (
        error is None
        and phase == "done"
        and bool(quality.get("overall_success"))
    )
    return {
        "source": str(source_path),
        "output_root": str(output_path),
        "profile": config.migration.profile,
        "scope": config.migration.scope,
        "phase": phase,
        "duration_seconds": round(duration, 2),
        "plan_items": len(plan_items),
        "applied_items": applied,
        "failed_items": failed,
        "quality": quality,
        "error": error,
        "success": success,
    }
