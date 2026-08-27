from __future__ import annotations

import json

from agent.config import VALID_IMPACT_LEVELS
from agent.context_loader import build_planning_context
from agent.llm import LLMClient, LLMError, parse_json_object
from agent.state import PlanItem

ALLOWED_ACTIONS = ("copy", "transform")
PLAN_MAX_TOKENS = 8192
PLAN_BATCH_SIZE = 5

PLAN_SYSTEM_PROMPT = (
    "你是企业级代码库迁移规划器。根据扫描出的文件清单输出迁移计划，"
    "必须返回 JSON 对象，格式为 "
    '{"items": [{"file": "...", "issue": "...", "action": "copy|transform", '
    '"impact": "low|medium|high", "evidence": {}}]}。'
    "file 必须是输入文件清单中的相对路径；"
    "action 只允许 copy 或 transform；"
    "impact 只允许 low、medium、high。不要输出其他内容。"
)


def build_fallback_plan(files: list[str]) -> list[PlanItem]:
    """无 LLM 或 LLM 失败时的回退计划：逐文件原样复制。"""
    return [
        PlanItem(
            id=f"p{index}",
            file=file,
            issue="骨架阶段回退计划：原样复制",
            action="copy",
            impact="low",
        )
        for index, file in enumerate(files, start=1)
    ]


def refactor_ratio(plan_items: list[PlanItem], file_lines: dict[str, int]) -> float:
    """计算计划中 transform 动作涉及的代码占比。"""
    total = sum(file_lines.values())
    if total <= 0:
        return 0.0
    changed = sum(
        file_lines[item.file]
        for item in plan_items
        if item.action == "transform" and item.file in file_lines
    )
    return changed / total


def build_plan_messages(
    files: list[str],
    evidence: list[dict] | None = None,
) -> list[dict[str, str]]:
    """组装规划阶段消息，注入入口文件、规则与技能上下文。"""
    context = build_planning_context()
    system = PLAN_SYSTEM_PROMPT
    if context:
        system += "\n\n以下为项目约束上下文，必须遵守：\n" + context

    payload: dict = {"files": files}
    if evidence:
        payload["evidence"] = evidence

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def generate_llm_plan(
    client: LLMClient,
    files: list[str],
    evidence: list[dict] | None = None,
    evidence_pool: list[str] | None = None,
) -> list[PlanItem]:
    """按批让大模型生成迁移计划，并严格校验每条计划。"""
    evidence_by_file = {entry.get("file"): entry for entry in (evidence or [])}
    plan: list[PlanItem] = []

    for start in range(0, len(files), PLAN_BATCH_SIZE):
        batch = files[start : start + PLAN_BATCH_SIZE]
        batch_evidence = [
            evidence_by_file[file]
            for file in batch
            if file in evidence_by_file
        ]
        batch_pool = _evidence_pool_from(batch_evidence) or evidence_pool
        plan.extend(
            _generate_batch(client, batch, batch_evidence, batch_pool)
        )

    for index, item in enumerate(plan, start=1):
        item.id = f"p{index}"
    return plan


def _generate_batch(
    client: LLMClient,
    files: list[str],
    evidence: list[dict],
    evidence_pool: list[str] | None,
) -> list[PlanItem]:
    """生成并校验一批文件的迁移计划。"""
    messages = build_plan_messages(files, evidence=evidence)
    raw = client.complete(
        messages,
        max_tokens=PLAN_MAX_TOKENS,
        json_mode=True,
    )
    try:
        payload = parse_json_object(raw)
    except LLMError as exc:
        raise LLMError(
            f"{exc}\n原始响应前 2000 字符: {raw[:2000]}"
        ) from exc

    items = payload.get("items")
    if not isinstance(items, list):
        raise LLMError("模型计划响应缺少 items 数组")

    allowed_files = set(files)
    plan: list[PlanItem] = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise LLMError(f"第 {index} 条计划不是 JSON 对象")

        file = str(raw.get("file", ""))
        if file not in allowed_files:
            raise LLMError(f"第 {index} 条计划引用了清单外文件: {file}")

        action = str(raw.get("action", ""))
        if action not in ALLOWED_ACTIONS:
            raise LLMError(f"第 {index} 条计划 action 非法: {action}")

        impact = str(raw.get("impact", ""))
        if impact not in VALID_IMPACT_LEVELS:
            raise LLMError(f"第 {index} 条计划 impact 非法: {impact}")

        evidence_data = raw.get("evidence")
        if action == "transform":
            if not isinstance(evidence_data, dict) or not evidence_data:
                raise LLMError(f"第 {index} 条计划缺少证据")
            if evidence_pool is not None:
                referenced = _evidence_doc_ids(evidence_data)
                if not referenced.intersection(set(evidence_pool)):
                    raise LLMError(f"第 {index} 条计划证据未关联检索命中")
        else:
            evidence_data = evidence_data if isinstance(evidence_data, dict) else {}

        plan.append(
            PlanItem(
                id=f"p{index}",
                file=file,
                issue=str(raw.get("issue", "未说明问题")),
                action=action,
                impact=impact,
                evidence=evidence_data,
            )
        )
    return plan


def _evidence_pool_from(evidence: list[dict]) -> list[str]:
    """从证据列表中汇总命中的文档 ID。"""
    pool: set[str] = set()
    for entry in evidence:
        for hit in entry.get("hits", []):
            doc_id = hit.get("doc_id")
            if doc_id:
                pool.add(doc_id)
    return sorted(pool)


def _evidence_doc_ids(evidence: dict) -> set[str]:
    """从证据结构中提取引用的文档 ID。"""
    referenced: set[str] = set()
    for value in evidence.values():
        if isinstance(value, str):
            referenced.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    referenced.add(item)
    return referenced
