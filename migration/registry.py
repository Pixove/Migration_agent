from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from migration.profiles.py3_upgrade.transform import transform_py3_upgrade
from migration.py2to3 import transform_python2_to_3

PROFILE_DEFS_DIR = Path(__file__).parent / "profile_defs"

_TRANSFORMS: dict[str, Callable[[str, Any], str]] = {
    "py2to3": transform_python2_to_3,
    "py3_upgrade": transform_py3_upgrade,
}


@dataclass
class MigrationProfile:
    name: str
    description: str
    transform: Callable[[str, Any], str] | None
    scopes: list[str]
    knowledge_base: list[str]
    rules: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    default_scope: str = ""
    priority: int = 0


@lru_cache(maxsize=1)
def get_profiles() -> dict[str, MigrationProfile]:
    """加载 migration/profile_defs/*.yaml 中的全部迁移档案。"""
    if not PROFILE_DEFS_DIR.is_dir():
        raise ValueError(f"迁移档案目录不存在: {PROFILE_DEFS_DIR}")

    profiles: dict[str, MigrationProfile] = {}
    paths = sorted(PROFILE_DEFS_DIR.glob("*.yaml")) + sorted(
        PROFILE_DEFS_DIR.glob("*.yml")
    )
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"读取迁移档案失败: {path}: {exc}") from exc
        profile = _parse_profile(data, path)
        if profile.name in profiles:
            raise ValueError(f"迁移档案名称重复: {profile.name}（{path}）")
        profiles[profile.name] = profile

    if not profiles:
        raise ValueError(f"未找到迁移档案定义: {PROFILE_DEFS_DIR}")

    return dict(
        sorted(
            profiles.items(),
            key=lambda item: (-item[1].priority, item[0]),
        )
    )


def _parse_profile(data: Any, path: Path) -> MigrationProfile:
    if not isinstance(data, dict):
        raise ValueError(f"迁移档案必须是对象: {path}")

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    scopes = _string_list(data.get("scopes"))
    knowledge_base = _string_list(data.get("knowledge_base"))
    rules = _string_list(data.get("rules"))
    if not name or not description or not scopes or not knowledge_base:
        raise ValueError(
            f"迁移档案缺少 name/description/scopes/knowledge_base: {path}"
        )

    transform_name = data.get("transform")
    if transform_name:
        transform_name = str(transform_name)
        if transform_name not in _TRANSFORMS:
            raise ValueError(
                f"迁移档案使用了未登记转换器 {transform_name}: {path}"
            )
        transform = _TRANSFORMS[transform_name]
    else:
        transform = None

    default_scope = str(data.get("default_scope") or scopes[0])
    if default_scope not in scopes:
        raise ValueError(
            f"迁移档案 default_scope={default_scope} 不在 scopes 中: {path}"
        )

    return MigrationProfile(
        name=name,
        description=description,
        transform=transform,
        scopes=scopes,
        knowledge_base=knowledge_base,
        rules=rules,
        keywords=_string_list(data.get("keywords")),
        default_scope=default_scope,
        priority=int(data.get("priority", 0)),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def load_profile(name: str) -> MigrationProfile:
    profiles = get_profiles()
    if name not in profiles:
        raise ValueError(
            f"未知迁移档案: {name}，可选: {sorted(profiles)}"
        )
    return profiles[name]
