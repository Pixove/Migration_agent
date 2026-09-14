from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agent.config import ConfigError, load_config
from agent.llm import LLMClient, LLMError, create_llm_client, parse_json_object
from migration.scan_signals import (
    ApiRule,
    RULES_DIR,
    load_api_rules,
    parse_api_rules,
)
from retrieval.documents import Document, RetrievalError, load_documents

DEFAULT_MAX_CHARS = 16000
DEFAULT_CANDIDATE_DIR = Path(__file__).parent / "rule_candidates"

RULE_AUTHOR_PROMPT = (
    "你是企业级代码迁移规则抽取器。请从给定知识文档中抽取可以用于 AST "
    "扫描的 API 迁移规则，严格返回 JSON："
    '{"rules": [{"id": "...", "kind": "deprecated_api", '
    '"type": "call|attribute|module|from_import", "name": "...", '
    '"module": "...", "replacement": "...", "message": "...", '
    '"docs": "...", "package": "...", "severity": "medium"}]}。\n'
    "要求：\n"
    "1. 只抽取文档明确说明的废弃 API、包拆分或替换关系；\n"
    "2. type=from_import 时必须提供 module 和 name；\n"
    "3. 不确定的规则不要输出；\n"
    "4. id 使用简短英文唯一标识；\n"
    "5. 不要输出 JSON 以外的任何内容。"
)


@dataclass
class CandidateReport:
    rules: list[ApiRule]
    errors: list[str]
    warnings: list[str]


def load_document_text(
    paths: list[str | Path],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[str, list[Document]]:
    """加载知识文档并拼接受限长度的抽取上下文。"""
    documents: list[Document] = []
    for path in paths:
        documents.extend(load_documents(path))
    parts = [
        f"[{document.doc_id}]\n{document.text}"
        for document in documents
        if document.text.strip()
    ]
    return "\n\n".join(parts)[:max_chars], documents


def extract_rule_candidates(
    text: str,
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """调用 LLM 从知识文档中抽取候选规则。"""
    messages = [
        {"role": "system", "content": RULE_AUTHOR_PROMPT},
        {
            "role": "user",
            "content": f"知识文档内容：\n{text}",
        },
    ]
    raw = llm.complete(messages, max_tokens=4096, json_mode=True)
    data = parse_json_object(raw)
    items = data.get("rules")
    if not isinstance(items, list):
        raise LLMError("规则抽取响应缺少 rules 列表")
    return [item for item in items if isinstance(item, dict)]


def validate_candidate_rules(
    items: list[dict[str, Any]],
    *,
    existing_rules: list[ApiRule] | None = None,
) -> CandidateReport:
    """校验候选规则并检测与现有规则的冲突。"""
    try:
        rules = list(parse_api_rules(items, source="<rule-candidates>"))
    except ValueError as exc:
        return CandidateReport(rules=[], errors=[str(exc)], warnings=[])

    existing = (
        existing_rules
        if existing_rules is not None
        else _load_all_active_rules()
    )
    errors: list[str] = []
    warnings: list[str] = []
    existing_ids = {rule.id for rule in existing}
    existing_keys = {_rule_key(rule): rule for rule in existing}
    seen_ids: set[str] = set()
    seen_keys: dict[tuple[str, str, str], ApiRule] = {}

    for rule in rules:
        if rule.id in existing_ids:
            errors.append(f"候选规则 ID 与现有规则重复: {rule.id}")
        if rule.id in seen_ids:
            errors.append(f"候选规则 ID 重复: {rule.id}")
        seen_ids.add(rule.id)

        key = _rule_key(rule)
        existing_rule = existing_keys.get(key)
        if existing_rule is not None:
            _record_conflict(
                errors,
                warnings,
                "现有规则",
                rule,
                existing_rule,
            )
        candidate_rule = seen_keys.get(key)
        if candidate_rule is not None:
            _record_conflict(
                errors,
                warnings,
                "候选规则",
                rule,
                candidate_rule,
            )
        seen_keys[key] = rule

    return CandidateReport(rules=rules, errors=errors, warnings=warnings)


def write_candidate_files(
    output: str | Path,
    candidates: list[dict[str, Any]],
    report: CandidateReport,
    *,
    source_paths: list[str | Path],
) -> tuple[Path, Path]:
    """写入候选 YAML 与人工评审报告，不自动激活规则。"""
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(
            {"rules": candidates},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    review = target.with_suffix(".review.md")
    lines = [
        "# 规则候选评审",
        "",
        "- 生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- 来源文档: " + ", ".join(str(path) for path in source_paths),
        f"- 候选数量: {len(candidates)}",
        f"- 校验通过: {len(report.rules)}",
        "",
    ]
    if report.errors:
        lines.append("## 错误")
        lines.append("")
        lines.extend(f"- {item}" for item in report.errors)
        lines.append("")
    if report.warnings:
        lines.append("## 警告")
        lines.append("")
        lines.extend(f"- {item}" for item in report.warnings)
        lines.append("")
    lines.append("## 候选规则")
    lines.append("")
    for rule in report.rules:
        lines.append(
            f"- `{rule.id}`: {rule.type} {rule.name} "
            f"-> {rule.replacement or '(见 docs)'}"
        )
    review.write_text("\n".join(lines), encoding="utf-8")
    return target, review


def _load_all_active_rules() -> list[ApiRule]:
    rules: list[ApiRule] = []
    for path in sorted(RULES_DIR.rglob("*.yaml")) + sorted(
        RULES_DIR.rglob("*.yml")
    ):
        rules.extend(load_api_rules(path))
    return rules


def _rule_key(rule: ApiRule) -> tuple[str, str, str]:
    return (rule.type, rule.module, rule.name)


def _record_conflict(
    errors: list[str],
    warnings: list[str],
    label: str,
    candidate: ApiRule,
    other: ApiRule,
) -> None:
    if candidate.replacement and other.replacement:
        if candidate.replacement != other.replacement:
            errors.append(
                f"{label}冲突: {candidate.id} 与 {other.id} 匹配同一 API "
                f"但 replacement 不同"
            )
            return
    warnings.append(
        f"{label}重复: {candidate.id} 与 {other.id} 匹配同一 API"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从知识文档抽取候选迁移规则（只生成待评审文件）"
    )
    parser.add_argument(
        "--docs",
        action="append",
        default=[],
        help="知识文档路径，可多次指定",
    )
    parser.add_argument(
        "--output",
        help="候选 YAML 输出路径，默认 migration/rule_candidates/",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径，默认 config.yaml",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="传给模型的文档最大字符数",
    )
    args = parser.parse_args(argv)

    if not args.docs:
        print("必须通过 --docs 指定至少一个知识文档")
        return 2
    try:
        config = load_config(args.config)
        llm = create_llm_client(config.llm)
    except (ConfigError, LLMError) as exc:
        print(f"初始化失败: {exc}")
        return 2

    try:
        text, documents = load_document_text(
            args.docs,
            max_chars=args.max_chars,
        )
    except (OSError, RetrievalError) as exc:
        print(f"加载知识文档失败: {exc}")
        return 1
    if not text:
        print("知识文档为空")
        return 1

    try:
        candidates = extract_rule_candidates(text, llm)
    except (LLMError, ValueError) as exc:
        print(f"规则抽取失败: {exc}")
        return 1
    report = validate_candidate_rules(candidates)

    output = Path(args.output) if args.output else (
        DEFAULT_CANDIDATE_DIR
        / f"candidates_{datetime.now():%Y%m%d_%H%M%S}.yaml"
    )
    yaml_path, review_path = write_candidate_files(
        output,
        candidates,
        report,
        source_paths=args.docs,
    )
    print(f"文档数量: {len(documents)}")
    print(f"候选规则: {len(candidates)}")
    print(f"候选文件: {yaml_path}")
    print(f"评审报告: {review_path}")
    if report.errors:
        print(f"存在 {len(report.errors)} 个错误，规则不会自动启用")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
