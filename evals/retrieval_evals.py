from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from agent.config import AppConfig, load_config
from migration.registry import load_profile
from retrieval.knowledge_base import KnowledgeBase

GOLDEN_FILE = Path(__file__).parent / "golden" / "retrieval.json"


def load_golden(path: str | Path = GOLDEN_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_retrieval_evals(
    config: AppConfig | None = None,
    top_k: int = 5,
    golden: dict | None = None,
) -> dict:
    """对 golden 查询计算 recall@K、nDCG 与 MRR。"""
    config = config or load_config("config.yaml")
    golden = golden or load_golden()
    profiles = golden.get("profiles")
    if profiles:
        per_profile = {
            name: _run_profile_evals(
                config,
                name,
                item,
                top_k=item.get("top_k", top_k),
            )
            for name, item in profiles.items()
        }
        all_cases = [
            case
            for report in per_profile.values()
            for case in report["cases"]
        ]
        return {
            "profiles": per_profile,
            "avg_recall": _avg(all_cases, "recall"),
            "avg_ndcg": _avg(all_cases, "ndcg"),
            "avg_mrr": _avg(all_cases, "mrr"),
        }
    return _run_profile_evals(
        config,
        golden.get("profile", "py2to3"),
        golden,
        top_k=top_k,
    )


def _run_profile_evals(
    config: AppConfig,
    profile: str,
    item: dict,
    top_k: int,
) -> dict:
    """对单个迁移档案的知识库运行检索评估。"""

    kb = KnowledgeBase(Path(tempfile.mkdtemp()) / "kb")
    for path in load_profile(profile).knowledge_base:
        kb.import_source(path)
    retriever = kb.build_retriever(config.retrieval)

    cases = []
    for query_item in item["queries"]:
        expected = set(query_item["expected"])
        hits = retriever.search(query_item["query"], top_k=top_k)
        retrieved = [hit.document.doc_id for hit in hits]
        cases.append(
            {
                "query": query_item["query"],
                "expected": query_item["expected"],
                "retrieved": retrieved,
                "recall": len(expected.intersection(retrieved)) / len(expected),
                "ndcg": _ndcg(retrieved, expected),
                "mrr": _mrr(retrieved, expected),
            }
        )

    return {
        "profile": profile,
        "top_k": top_k,
        "cases": cases,
        "avg_recall": _avg(cases, "recall"),
        "avg_ndcg": _avg(cases, "ndcg"),
        "avg_mrr": _avg(cases, "mrr"),
    }


def _ndcg(retrieved: list[str], expected: set[str]) -> float:
    dcg = sum(
        1.0 / math.log2(index + 2)
        for index, doc_id in enumerate(retrieved)
        if doc_id in expected
    )
    ideal = min(len(retrieved), len(expected))
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def _mrr(retrieved: list[str], expected: set[str]) -> float:
    for index, doc_id in enumerate(retrieved):
        if doc_id in expected:
            return 1.0 / (index + 1)
    return 0.0


def _avg(cases: list[dict], key: str) -> float:
    if not cases:
        return 0.0
    return sum(case[key] for case in cases) / len(cases)
