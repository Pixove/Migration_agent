from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Phase(str, Enum):
    INIT = "init"
    SCAN = "scan"
    RETRIEVE = "retrieve"
    PLAN = "plan"
    APPLY = "apply"
    VERIFY = "verify"
    REPORT = "report"
    DONE = "done"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.INIT: {Phase.SCAN, Phase.FAILED},
    Phase.SCAN: {Phase.RETRIEVE, Phase.FAILED},
    Phase.RETRIEVE: {Phase.PLAN, Phase.FAILED},
    Phase.PLAN: {Phase.APPLY, Phase.FAILED},
    Phase.APPLY: {Phase.VERIFY, Phase.FAILED},
    Phase.VERIFY: {Phase.APPLY, Phase.REPORT, Phase.FAILED},
    Phase.REPORT: {Phase.DONE, Phase.FAILED},
    Phase.DONE: set(),
    Phase.FAILED: set(),
}


@dataclass
class PlanItem:
    id: str
    file: str
    issue: str
    action: str
    impact: str
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    output_file: str | None = None
    error: str | None = None


@dataclass
class AuditEntry:
    timestamp: str
    phase: str
    tool: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class MigrationState:
    """任务状态机与审计记录。"""

    def __init__(
        self,
        source_root: str | Path,
        output_root: str | Path,
        audit_dir_name: str = ".migration-agent",
    ) -> None:
        self.source_root = Path(source_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.audit_dir_name = audit_dir_name
        self.created_at = _now()
        self.updated_at = self.created_at
        self.phase = Phase.INIT
        self.plan_items: list[PlanItem] = []
        self.audit_entries: list[AuditEntry] = []
        self.unresolved_signals: list[dict] = []

    def transition(self, target: Phase) -> None:
        if target == Phase.FAILED:
            self.phase = Phase.FAILED
            self._touch()
            return
        if target not in ALLOWED_TRANSITIONS[self.phase]:
            raise ValueError(
                f"非法状态迁移: {self.phase.value} -> {target.value}"
            )
        self.phase = target
        self._touch()

    def add_audit(
        self,
        tool: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.audit_entries.append(
            AuditEntry(
                timestamp=_now(),
                phase=self.phase.value,
                tool=tool,
                message=message,
                detail=detail or {},
            )
        )
        self._touch()

    def add_plan_item(self, item: PlanItem) -> None:
        self.plan_items.append(item)
        self._touch()

    def audit_dir(self) -> Path:
        return self.output_root / self.audit_dir_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_root": str(self.source_root),
            "output_root": str(self.output_root),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "phase": self.phase.value,
            "plan_items": [asdict(item) for item in self.plan_items],
            "audit_entries": [asdict(entry) for entry in self.audit_entries],
            "unresolved_signals": self.unresolved_signals,
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "MigrationState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        state = cls(
            source_root=data["source_root"],
            output_root=data["output_root"],
            audit_dir_name=data.get("audit_dir_name", ".migration-agent"),
        )
        state.created_at = data.get("created_at", state.created_at)
        state.updated_at = data.get("updated_at", state.updated_at)
        state.phase = Phase(data["phase"])
        state.plan_items = [
            PlanItem(**item) for item in data.get("plan_items", [])
        ]
        state.audit_entries = [
            AuditEntry(**entry) for entry in data.get("audit_entries", [])
        ]
        state.unresolved_signals = data.get("unresolved_signals", [])
        return state

    def _touch(self) -> None:
        self.updated_at = _now()


class AuditWorkspace:
    """负责创建输出目录与审计目录，并管理状态文件位置。"""

    def __init__(self, state: MigrationState) -> None:
        self.state = state

    def initialize(self) -> Path:
        audit_dir = self.state.audit_dir()
        audit_dir.mkdir(parents=True, exist_ok=True)
        self.state.add_audit("workspace", "审计工作区初始化完成")
        return audit_dir

    def state_path(self) -> Path:
        return self.state.audit_dir() / "state.json"

    def log_path(self) -> Path:
        return self.state.audit_dir() / "audit.log"

    def save_state(self) -> None:
        self.state.save(self.state_path())

    def append_log(self, line: str) -> None:
        with self.log_path().open("a", encoding="utf-8") as handle:
            handle.write(f"{_now()} {line}\n")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
