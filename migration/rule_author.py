from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agent.config import ConfigError, load_config
from agent.llm import LLMClient, LLMError, create_llm_client, parse_json_object
from migration.registry import get_profiles, parse_profile_definition
from migration.scan_signals import (
    ApiRule,
    RULES_DIR,
    load_api_rules,
    parse_api_rules,
    scan_python_signals,
)
from retrieval.documents import Document, RetrievalError, load_documents

DEFAULT_MAX_CHARS = 16000
DEFAULT_CANDIDATE_DIR = Path(__file__).parent / "rule_candidates"
DEFAULT_PROFILE_CANDIDATE_DIR = Path(__file__).parent / "profile_candidates"

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
    profile_candidate: dict[str, Any] | None = None,
    profile_path: str | Path | None = None,
    profile_errors: list[str] | None = None,
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
    if profile_candidate is not None:
        lines.append("## 档案候选")
        lines.append("")
        lines.append(f"- 候选文件: `{profile_path}`")
        lines.append(
            "- 正式规则路径: "
            + ", ".join(profile_candidate.get("rules", []))
        )
        if profile_errors:
            lines.append("- 校验错误:")
            lines.extend(f"  - {item}" for item in profile_errors)
        else:
            lines.append("- 校验: 通过")
        lines.append("")
    lines.append("## 候选规则")
    lines.append("")
    for rule in report.rules:
        lines.append(
            f"- `{rule.id}`: {rule.type} {rule.name} "
            f"-> {rule.replacement or '(见 docs)'}"
        )
    lines.append("")
    lines.append("## 启用步骤")
    lines.append("")
    lines.append("1. 评审候选规则和档案定义；")
    lines.append("2. 将规则移到 `migration/rules/profiles/<name>.yaml`；")
    lines.append("3. 将档案移到 `migration/profile_defs/<name>.yaml`；")
    lines.append("4. 运行测试与 `evals.run`。")
    review.write_text("\n".join(lines), encoding="utf-8")
    return target, review


def build_profile_candidate(
    name: str,
    candidates: list[dict[str, Any]],
    source_paths: list[str | Path],
    *,
    description: str = "",
    scopes: list[str] | None = None,
    default_scope: str = "",
    knowledge_base: list[str] | None = None,
    keywords: list[str] | None = None,
    transform: str | None = None,
    priority: int = 20,
) -> dict[str, Any]:
    """根据候选规则和知识文档构造候选档案定义。"""
    if not name.strip():
        raise ValueError("档案名不能为空")
    scope_list = scopes or (
        ["deprecated_api"] if candidates else ["syntax"]
    )
    default = default_scope or scope_list[0]
    return {
        "name": name,
        "description": description or f"从知识文档生成的迁移档案: {name}",
        "transform": transform,
        "scopes": scope_list,
        "default_scope": default,
        "knowledge_base": knowledge_base
        or _default_knowledge_base(source_paths),
        "rules": (
            [f"migration/rules/profiles/{name}.yaml"]
            if candidates
            else []
        ),
        "keywords": keywords or [name, name.replace("_", " ")],
        "priority": priority,
    }


def write_profile_candidate(
    output: str | Path,
    profile: dict[str, Any],
) -> Path:
    """写入候选档案定义，不自动注册。"""
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


def evaluate_candidate_coverage(
    candidate_path: str | Path,
    target_path: str | Path,
) -> dict[str, Any]:
    """用候选规则扫描目标项目，返回候选规则的命中与缺失情况。"""
    candidate_file = Path(candidate_path)
    data = yaml.safe_load(candidate_file.read_text(encoding="utf-8")) or {}
    candidate_rules = list(
        parse_api_rules(data.get("rules"), source=candidate_file)
    )
    candidate_apis = {_rule_api(rule) for rule in candidate_rules}

    target = Path(target_path)
    files = (
        [target]
        if target.is_file()
        else sorted(target.rglob("*.py"))
    )
    detected: set[str] = set()
    for file in files:
        if not file.is_file():
            continue
        signals = scan_python_signals(
            file.read_text(encoding="utf-8-sig", errors="ignore"),
            file.as_posix(),
            rules_path=[RULES_DIR, candidate_file],
        )
        detected.update(
            str(signal.get("api", ""))
            for signal in signals
            if signal.get("api")
        )

    matched = sorted(candidate_apis.intersection(detected))
    missing = sorted(candidate_apis - detected)
    return {
        "target": str(target),
        "file_count": len([file for file in files if file.is_file()]),
        "candidate_count": len(candidate_apis),
        "matched_count": len(matched),
        "matched": matched,
        "missing": missing,
    }


def append_coverage_sections(
    review_path: str | Path,
    coverages: list[dict[str, Any]],
) -> None:
    """把候选覆盖验证结果追加到评审报告。"""
    if not coverages:
        return
    lines = ["", "## 候选覆盖验证", ""]
    for coverage in coverages:
        lines.append(f"### {coverage['target']}")
        lines.append("")
        lines.append(f"- 扫描文件: {coverage['file_count']}")
        lines.append(f"- 候选规则: {coverage['candidate_count']}")
        lines.append(f"- 命中: {coverage['matched_count']}")
        if coverage["missing"]:
            lines.append("- 未命中:")
            lines.extend(f"  - {item}" for item in coverage["missing"])
        else:
            lines.append("- 未命中: 无")
        lines.append("")
    with Path(review_path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def approve_candidates(
    rules_candidate: str | Path,
    *,
    rules_target: str | Path | None = None,
    profile_candidate: str | Path | None = None,
    profile_target: str | Path | None = None,
    force: bool = False,
) -> tuple[Path, Path | None]:
    """显式批准后，把候选规则/档案复制到正式目录。"""
    rules_source = Path(rules_candidate)
    rules_data = yaml.safe_load(
        rules_source.read_text(encoding="utf-8")
    ) or {}
    report = validate_candidate_rules(
        rules_data.get("rules", []),
    )
    if report.errors:
        raise ValueError("候选规则校验失败: " + "; ".join(report.errors))

    parsed_profile = None
    profile_source: Path | None = None
    if profile_candidate:
        profile_source = Path(profile_candidate)
        profile_data = yaml.safe_load(
            profile_source.read_text(encoding="utf-8")
        ) or {}
        parsed_profile = parse_profile_definition(
            profile_data,
            source=profile_source,
        )
        if parsed_profile.name in get_profiles() and not force:
            raise ValueError(f"档案已存在: {parsed_profile.name}")
        if rules_target is None and parsed_profile.rules:
            rules_target = parsed_profile.rules[0]

    if not rules_target:
        raise ValueError("缺少 rules_target，无法确定正式规则路径")
    rules_target_path = Path(rules_target)
    profile_target_path: Path | None = None
    if parsed_profile is not None:
        if profile_target is None:
            profile_target = (
                Path(__file__).parent
                / "profile_defs"
                / f"{parsed_profile.name}.yaml"
            )
        profile_target_path = Path(profile_target)
        rule_paths = {
            Path(item).as_posix() for item in parsed_profile.rules
        }
        if rules_target_path.as_posix() not in rule_paths:
            raise ValueError(
                "候选档案 rules 未引用目标规则路径: "
                f"{rules_target_path.as_posix()}"
            )

    targets = [rules_target_path]
    if profile_target_path is not None:
        targets.append(profile_target_path)
    if not force:
        for target in targets:
            if target.exists():
                raise ValueError(
                    f"目标文件已存在，使用 --force 覆盖: {target}"
                )

    rules_target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rules_source, rules_target_path)
    if profile_source is not None and profile_target_path is not None:
        profile_target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile_source, profile_target_path)
    return rules_target_path, profile_target_path


def _rule_api(rule: ApiRule) -> str:
    if rule.type == "from_import":
        return f"{rule.module}.{rule.name}"
    return rule.name


def _default_knowledge_base(paths: list[str | Path]) -> list[str]:
    roots: list[str] = []
    for path in paths:
        target = Path(path)
        root = target if target.is_dir() else target.parent
        text = root.as_posix()
        if text not in roots:
            roots.append(text)
    return roots


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
        description=(
            "从知识文档抽取候选迁移规则（只生成待评审文件）。"
            "生成模式至少需要 --docs；审批模式需要 --approve 和 "
            "--rules-candidate。"
        ),
        epilog=(
            "示例：\n"
            "  生成候选：python -m migration.rule_author "
            "--docs guide.md [--profile-name name]\n"
            "  审批安装：python -m migration.rule_author --approve "
            "--rules-candidate candidates.yaml "
            "[--profile-candidate profile.yaml]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--docs",
        action="append",
        default=[],
        help="知识文档路径，生成模式必填，可多次指定",
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
    parser.add_argument(
        "--profile-name",
        help="可选；同时生成候选档案时的档案名",
    )
    parser.add_argument(
        "--profile-output",
        help="候选档案输出路径，默认 migration/profile_candidates/",
    )
    parser.add_argument(
        "--knowledge-base",
        action="append",
        default=[],
        help="候选档案引用的知识库目录，可多次指定",
    )
    parser.add_argument(
        "--description",
        default="",
        help="候选档案描述",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="候选档案关键词，可多次指定",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="候选档案范围，可多次指定",
    )
    parser.add_argument(
        "--transform",
        help="候选档案转换器名称，默认为空",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=20,
        help="候选档案关键词匹配优先级",
    )
    parser.add_argument(
        "--verify-against",
        action="append",
        default=[],
        help="用候选规则扫描目标文件或目录，可多次指定",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="进入审批模式，批准候选文件并复制到正式目录",
    )
    parser.add_argument(
        "--rules-candidate",
        help="审批模式必填；要批准的候选规则 YAML",
    )
    parser.add_argument(
        "--rules-target",
        help="可选；没有档案规则路径可推导时必填",
    )
    parser.add_argument(
        "--profile-candidate",
        help="要批准的候选档案 YAML",
    )
    parser.add_argument(
        "--profile-target",
        help="正式档案目标路径",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="批准时覆盖已存在的目标文件",
    )
    args = parser.parse_args(argv)

    if args.approve:
        if not args.rules_candidate:
            print("批准模式必须提供 --rules-candidate")
            return 2
        try:
            rules_target, profile_target = approve_candidates(
                args.rules_candidate,
                rules_target=args.rules_target,
                profile_candidate=args.profile_candidate,
                profile_target=args.profile_target,
                force=args.force,
            )
        except (OSError, ValueError) as exc:
            print(f"批准失败: {exc}")
            return 1
        print(f"正式规则: {rules_target}")
        if profile_target is not None:
            print(f"正式档案: {profile_target}")
        print("请运行测试与 evals.run 后再提交。")
        return 0

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

    profile_candidate: dict[str, Any] | None = None
    profile_path: Path | None = None
    profile_errors: list[str] = []
    if args.profile_name:
        if args.profile_name in get_profiles():
            print(f"档案已存在，拒绝生成候选: {args.profile_name}")
            return 1
        profile_candidate = build_profile_candidate(
            args.profile_name,
            candidates,
            args.docs,
            description=args.description,
            scopes=args.scope or None,
            knowledge_base=args.knowledge_base or None,
            keywords=args.keyword or None,
            transform=args.transform,
            priority=args.priority,
        )
        try:
            parse_profile_definition(
                profile_candidate,
                source="<profile-candidate>",
            )
        except ValueError as exc:
            profile_errors.append(str(exc))
        profile_path = Path(args.profile_output) if args.profile_output else (
            DEFAULT_PROFILE_CANDIDATE_DIR
            / f"{args.profile_name}.yaml"
        )
        write_profile_candidate(profile_path, profile_candidate)

    output = Path(args.output) if args.output else (
        DEFAULT_CANDIDATE_DIR
        / f"candidates_{datetime.now():%Y%m%d_%H%M%S}.yaml"
    )
    yaml_path, review_path = write_candidate_files(
        output,
        candidates,
        report,
        source_paths=args.docs,
        profile_candidate=profile_candidate,
        profile_path=profile_path,
        profile_errors=profile_errors,
    )
    coverages = [
        evaluate_candidate_coverage(yaml_path, target)
        for target in args.verify_against
    ]
    append_coverage_sections(review_path, coverages)
    print(f"文档数量: {len(documents)}")
    print(f"候选规则: {len(candidates)}")
    print(f"候选文件: {yaml_path}")
    if profile_path is not None:
        print(f"候选档案: {profile_path}")
    print(f"评审报告: {review_path}")
    for coverage in coverages:
        print(
            f"覆盖验证 {coverage['target']}: "
            f"{coverage['matched_count']}/{coverage['candidate_count']} 命中"
        )
    if report.errors or profile_errors:
        print(
            f"存在 {len(report.errors) + len(profile_errors)} 个错误，"
            "候选不会自动启用"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
