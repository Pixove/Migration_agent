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
    profile = golden.get("profile", "py2to3")

    kb = KnowledgeBase(Path(tempfile.mkdtemp()) / "kb")
    for path in load_profile(profile).knowledge_base:
        kb.import_source(path)
    retriever = kb.build_retriever(config.retrieval)

    cases = []
    for item in golden["queries"]:
        expected = set(item["expected"])
        hits = retriever.search(item["query"], top_k=top_k)
        retrieved = [hit.document.doc_id for hit in hits]
        cases.append(
            {
                "query": item["query"],
                "expected": item["expected"],
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
