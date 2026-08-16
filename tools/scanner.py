from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.config import GuardrailsConfig
from agent.guardrails import PathGuard


@dataclass
class FileInfo:
    relative_path: str
    extension: str
    size_bytes: int
    line_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
        }


def scan_project(
    source_root: str | Path,
    config: GuardrailsConfig,
    guard: PathGuard | None = None,
) -> list[FileInfo]:
    """扫描输入项目，按护栏规则过滤目录、扩展名与文件大小。"""
    root = Path(source_root).resolve()
    denied_extensions = {ext.lower() for ext in config.deny_extensions}
    excluded_names = set(config.excluded_dirs)
    max_bytes = config.max_file_size_mb * 1024 * 1024
    files: list[FileInfo] = []

    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = [name for name in dirnames if name not in excluded_names]
        for filename in sorted(filenames):
            full_path = Path(dirpath) / filename
            suffix = full_path.suffix.lower()
            if suffix in denied_extensions:
                continue

            try:
                size = full_path.stat().st_size
            except OSError:
                continue
            if size > max_bytes:
                continue

            relative = full_path.relative_to(root).as_posix()
            if guard is not None:
                guard.resolve_source(relative)

            files.append(
                FileInfo(
                    relative_path=relative,
                    extension=suffix,
                    size_bytes=size,
                    line_count=_count_lines(full_path),
                )
            )

    return files


def _count_lines(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return len(text.splitlines())
