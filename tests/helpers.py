from __future__ import annotations

from pathlib import Path

from agent.config import load_config as _load_config


def load_config(path: str | Path):
    """让测试始终使用受版本控制的示例配置，隔离本地 config.yaml。"""
    if Path(path) == Path("config.yaml"):
        path = "config.example.yaml"
    return _load_config(path)
