from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.guardrails import Budget, GuardrailError, ToolRegistry


@dataclass
class ToolResult:
    success: bool
    tool: str
    result: Any = None
    error: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., Any]
    max_calls: int = 10


class ToolDispatcher:
    """工具调度器：白名单校验、名称映射、调用计数与错误捕获。"""

    def __init__(
        self,
        registry: ToolRegistry,
        budget: Budget | None = None,
    ) -> None:
        self.registry = registry
        self.budget = budget
        self._tools: dict[str, ToolSpec] = {}
        self._call_counts: dict[str, int] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec
        self._call_counts.setdefault(spec.name, 0)

    def available(self) -> list[str]:
        return sorted(self._tools)

    def call_counts(self) -> dict[str, int]:
        return dict(self._call_counts)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        self.registry.assert_allowed(name)

        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(
                success=False,
                tool=name,
                error=f"工具未注册: {name}",
            )

        if self._call_counts[name] >= spec.max_calls:
            return ToolResult(
                success=False,
                tool=name,
                error=f"工具调用次数超过上限 {spec.max_calls}",
            )

        self._call_counts[name] += 1
        try:
            result = spec.fn(**kwargs)
            return ToolResult(success=True, tool=name, result=result)
        except Exception as exc:
            return ToolResult(success=False, tool=name, error=str(exc))
