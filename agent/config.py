from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_PROVIDERS = ("openai", "ollama")
VALID_IMPACT_LEVELS = ("low", "medium", "high")


class ConfigError(Exception):
    """配置文件缺失或内容非法时抛出。"""


@dataclass
class LLMConfig:
    provider: str = "openai"
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout_seconds: int = 120
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"


@dataclass
class WorkspaceConfig:
    audit_dir_name: str = ".migration-agent"
    max_plan_items: int = 50
    max_retries_per_item: int = 3
    max_total_patches: int = 200


@dataclass
class RetrievalConfig:
    kb_dir: str = "kb"
    bm25_enabled: bool = True
    bm25_top_k: int = 20
    vector_enabled: bool = False
    vector_top_k: int = 20
    embedding_model: str = "text-embedding-3-small"
    rerank_enabled: bool = True
    rerank_top_k: int = 5
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass
class MigrationConfig:
    profile: str = "py2to3"
    scope: str = "syntax"


@dataclass
class GuardrailsConfig:
    allowed_tools: list[str] = field(
        default_factory=lambda: [
            "scan_files",
            "retrieve_examples",
            "propose_plan",
            "apply_patch",
            "run_verifier",
            "write_report",
        ]
    )
    auto_apply_max_impact: str = "low"
    require_approval_impact: list[str] = field(default_factory=lambda: ["medium", "high"])
    max_refactor_ratio: float = 0.3
    deny_extensions: list[str] = field(
        default_factory=lambda: [".pyc", ".pdb", ".exe", ".dll", ".so", ".dylib", ".bin", ".dat"]
    )
    max_file_size_mb: int = 5
    excluded_dirs: list[str] = field(
        default_factory=lambda: [
            ".git",
            "node_modules",
            "__pycache__",
            "venv",
            ".venv",
            "dist",
            "build",
            ".migration-agent",
        ]
    )


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    migration: MigrationConfig = field(default_factory=MigrationConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise ConfigError("缺少依赖 pyyaml，请先执行: pip install pyyaml") from exc

    if not path.is_file():
        raise ConfigError(f"配置文件不存在: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ConfigError("配置文件根节点必须是键值映射")
    return data


def _get(mapping: dict[str, Any], key: str, default: Any) -> Any:
    value = mapping.get(key, default)
    return default if value is None else value


def _build_llm_config(section: dict[str, Any]) -> LLMConfig:
    provider = _get(section, "provider", "openai")
    if provider not in VALID_PROVIDERS:
        raise ConfigError(f"llm.provider 不合法: {provider}，可选值: {VALID_PROVIDERS}")

    openai = _get(section, "openai", {}) or {}
    ollama = _get(section, "ollama", {}) or {}

    return LLMConfig(
        provider=provider,
        temperature=float(_get(section, "temperature", 0.2)),
        max_tokens=int(_get(section, "max_tokens", 2048)),
        timeout_seconds=int(_get(section, "timeout_seconds", 120)),
        openai_base_url=str(_get(openai, "base_url", "https://api.openai.com/v1")),
        openai_api_key_env=str(_get(openai, "api_key_env", "OPENAI_API_KEY")),
        openai_model=str(_get(openai, "model", "gpt-4o-mini")),
        ollama_base_url=str(_get(ollama, "base_url", "http://localhost:11434")),
        ollama_model=str(_get(ollama, "model", "qwen2.5:7b")),
    )


def _build_workspace_config(section: dict[str, Any]) -> WorkspaceConfig:
    return WorkspaceConfig(
        audit_dir_name=str(_get(section, "audit_dir_name", ".migration-agent")),
        max_plan_items=int(_get(section, "max_plan_items", 50)),
        max_retries_per_item=int(_get(section, "max_retries_per_item", 3)),
        max_total_patches=int(_get(section, "max_total_patches", 200)),
    )


def _build_retrieval_config(section: dict[str, Any]) -> RetrievalConfig:
    bm25 = _get(section, "bm25", {}) or {}
    vector = _get(section, "vector", {}) or {}
    rerank = _get(section, "rerank", {}) or {}

    return RetrievalConfig(
        kb_dir=str(_get(section, "kb_dir", "kb")),
        bm25_enabled=bool(_get(bm25, "enabled", True)),
        bm25_top_k=int(_get(bm25, "top_k", 20)),
        vector_enabled=bool(_get(vector, "enabled", False)),
        vector_top_k=int(_get(vector, "top_k", 20)),
        embedding_model=str(_get(vector, "embedding_model", "text-embedding-3-small")),
        rerank_enabled=bool(_get(rerank, "enabled", True)),
        rerank_top_k=int(_get(rerank, "top_k", 5)),
        rerank_model=str(_get(rerank, "model", "cross-encoder/ms-marco-MiniLM-L-6-v2")),
    )


def _build_migration_config(section: dict[str, Any]) -> MigrationConfig:
    return MigrationConfig(
        profile=str(_get(section, "profile", "py2to3")),
        scope=str(_get(section, "scope", "syntax")),
    )


def _build_guardrails_config(section: dict[str, Any]) -> GuardrailsConfig:
    tools = _get(section, "allowed_tools", None)
    if not tools:
        raise ConfigError("guardrails.allowed_tools 不能为空")

    impact = _get(section, "auto_apply_max_impact", "low")
    if impact not in VALID_IMPACT_LEVELS:
        raise ConfigError(f"guardrails.auto_apply_max_impact 不合法: {impact}")

    approval_impacts = _get(section, "require_approval_impact", ["medium", "high"])
    invalid = [item for item in approval_impacts if item not in VALID_IMPACT_LEVELS]
    if invalid:
        raise ConfigError(f"guardrails.require_approval_impact 包含非法等级: {invalid}")

    return GuardrailsConfig(
        allowed_tools=list(tools),
        auto_apply_max_impact=impact,
        require_approval_impact=list(approval_impacts),
        max_refactor_ratio=float(_get(section, "max_refactor_ratio", 0.3)),
        deny_extensions=list(_get(section, "deny_extensions", [])),
        max_file_size_mb=int(_get(section, "max_file_size_mb", 5)),
        excluded_dirs=list(_get(section, "excluded_dirs", [])),
    )


def load_config(path: str | Path) -> AppConfig:
    """从 YAML 文件加载并校验全局配置。"""
    target = Path(path)
    if not target.is_file() and target.name == "config.yaml":
        example = target.parent / "config.example.yaml"
        if example.is_file():
            target = example
    data = _read_yaml(target)
    return AppConfig(
        llm=_build_llm_config(_get(data, "llm", {})),
        migration=_build_migration_config(_get(data, "migration", {})),
        workspace=_build_workspace_config(_get(data, "workspace", {})),
        retrieval=_build_retrieval_config(_get(data, "retrieval", {})),
        guardrails=_build_guardrails_config(_get(data, "guardrails", {})),
    )


def api_key_for(config: LLMConfig) -> str:
    """读取 OpenAI 兼容服务所需的 API 密钥环境变量。"""
    return os.environ.get(config.openai_api_key_env, "")
