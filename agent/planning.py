from __future__ import annotations

import json

from agent.config import VALID_IMPACT_LEVELS
from agent.context_loader import build_planning_context
from agent.llm import LLMClient, LLMError
from agent.state import PlanItem

ALLOWED_ACTIONS = ("copy", "transform")

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


def generate_llm_plan(client: LLMClient, files: list[str]) -> list[PlanItem]:
    """让大模型生成迁移计划，并严格校验每条计划。"""
    messages = build_plan_messages(files)
    payload = client.complete_json(messages, max_tokens=4096)
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

        evidence = raw.get("evidence")
        plan.append(
            PlanItem(
                id=f"p{index}",
                file=file,
                issue=str(raw.get("issue", "未说明问题")),
                action=action,
                impact=impact,
                evidence=evidence if isinstance(evidence, dict) else {},
            )
        )
    return plan
