from __future__ import annotations

import json

from agent.context_loader import build_document_index, build_red_lines
from agent.llm import LLMClient, LLMError, parse_json_object

REVIEW_PROMPT = (
    "你是企业级代码迁移评审员。请审查一条语义编辑是否合理，"
    "必须返回 JSON："
    '{"approved": true/false, "issues": ["..."]}。\n'
    "检查要点：\n"
    "1. 改动是否只在声明的文件和行范围内；\n"
    "2. 证据是否与改动相关；\n"
    "3. 是否引入无关改动；\n"
    "4. 是否明显语法或逻辑错误；\n"
    "5. 不确定时 approved 必须为 false。\n"
    "不要输出其他内容。"
)


def review_edit(llm: LLMClient, item: dict, diff: str) -> dict:
    """评审一条语义编辑，解析失败或格式非法时按不通过处理。"""
    index = build_document_index()
    red_lines = build_red_lines()
    messages = [
        {
            "role": "system",
            "content": f"{REVIEW_PROMPT}\n\n{index}\n\n{red_lines}",
        },
        {
            "role": "user",
            "content": json.dumps(
                {"item": item, "diff": diff},
                ensure_ascii=False,
            ),
        },
    ]
    try:
        raw = llm.complete(messages, max_tokens=1024, json_mode=True)
        data = parse_json_object(raw)
    except LLMError:
        return {"approved": False, "issues": ["评审响应解析失败"]}
    if not isinstance(data, dict):
        return {"approved": False, "issues": ["评审响应格式非法"]}
    issues = data.get("issues")
    return {
        "approved": bool(data.get("approved")),
        "issues": issues if isinstance(issues, list) else [],
    }
