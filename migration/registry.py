from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from migration.profiles.py3_upgrade.transform import transform_py3_upgrade
from migration.py2to3 import transform_python2_to_3


@dataclass
class MigrationProfile:
    name: str
    description: str
    transform: Callable[[str, Any], str] | None
    scopes: list[str]


def get_profiles() -> dict[str, MigrationProfile]:
    """返回全部已注册的迁移档案。"""
    return {
        "py2to3": MigrationProfile(
            name="py2to3",
            description="Python 2 到 Python 3 基础语法迁移（历史档案）",
            transform=transform_python2_to_3,
            scopes=["syntax"],
        ),
        "py3_upgrade": MigrationProfile(
            name="py3_upgrade",
            description="Python 3.x 升级迁移（废弃 API 与新语法）",
            transform=transform_py3_upgrade,
            scopes=["syntax", "deprecated_api"],
        ),
    }


def load_profile(name: str) -> MigrationProfile:
    profiles = get_profiles()
    if name not in profiles:
        raise ValueError(
            f"未知迁移档案: {name}，可选: {sorted(profiles)}"
        )
    return profiles[name]
