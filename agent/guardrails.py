from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.config import GuardrailsConfig, VALID_IMPACT_LEVELS


class GuardrailError(Exception):
    """违反护栏约束时抛出。"""


class BudgetExceeded(GuardrailError):
    """任务预算耗尽。"""


class PathGuard:
    """路径沙箱：输入项目只读，输出目录为唯一可写区域。"""

    def __init__(self, source_root: str | Path, output_root: str | Path) -> None:
        self.source_root = Path(source_root).resolve()
        self.output_root = Path(output_root).resolve()
        self._validate_roots()

    def _validate_roots(self) -> None:
        if self.source_root == self.output_root:
            raise GuardrailError("输入路径与输出路径不能相同")

        try:
            self.source_root.relative_to(self.output_root)
        except ValueError:
            pass
        else:
            raise GuardrailError("输出路径不能包含输入项目")

        try:
            self.output_root.relative_to(self.source_root)
        except ValueError:
            pass
        else:
            raise GuardrailError("输出路径不能位于输入项目内部")

    def resolve_source(self, relative: str | Path) -> Path:
        """将相对路径解析到输入项目根内，越界即拒绝。"""
        self._assert_relative(relative)
        path = (self.source_root / relative).resolve()
        self._assert_within(path, self.source_root, "输入项目")
        return path

    def resolve_output(self, relative: str | Path) -> Path:
        """将相对路径解析到输出目录根内，越界即拒绝。"""
        self._assert_relative(relative)
        path = (self.output_root / relative).resolve()
        self._assert_within(path, self.output_root, "输出目录")
        return path

    @staticmethod
    def _assert_relative(relative: str | Path) -> None:
        path = Path(relative)
        if path.is_absolute():
            raise GuardrailError(f"只接受相对路径，收到绝对路径: {relative}")

    @staticmethod
    def _assert_within(path: Path, root: Path, label: str) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise GuardrailError(f"路径越界: {path} 不在{label}内") from exc


class ToolRegistry:
    """工具白名单：白名单之外的调用一律拒绝。"""

    def __init__(self, allowed_tools: list[str]) -> None:
        self.allowed = set(allowed_tools)

    def assert_allowed(self, tool_name: str) -> None:
        if tool_name not in self.allowed:
            raise GuardrailError(f"工具不在白名单内: {tool_name}")


@dataclass
class Budget:
    """任务预算：限制计划条目、重试次数与补丁总数。"""

    max_plan_items: int
    max_retries_per_item: int
    max_total_patches: int
    plan_items_used: int = 0
    retries_used: int = 0
    patches_used: int = 0

    def check_plan_item(self) -> None:
        if self.plan_items_used >= self.max_plan_items:
            raise BudgetExceeded(
                f"计划条目超过上限 {self.max_plan_items}，请拆分任务"
            )

    def record_plan_item(self) -> None:
        self.check_plan_item()
        self.plan_items_used += 1

    def check_retry(self) -> None:
        if self.retries_used >= self.max_retries_per_item:
            raise BudgetExceeded(
                f"单条计划重试次数超过上限 {self.max_retries_per_item}"
            )

    def record_retry(self) -> None:
        self.check_retry()
        self.retries_used += 1

    def check_patch(self) -> None:
        if self.patches_used >= self.max_total_patches:
            raise BudgetExceeded(f"补丁总数超过上限 {self.max_total_patches}")

    def record_patch(self) -> None:
        self.check_patch()
        self.patches_used += 1


class ApprovalPolicy:
    """影响面审批策略：低影响自动执行，中高影响需要人工审批。"""

    def __init__(self, config: GuardrailsConfig) -> None:
        self.auto_apply_max_impact = config.auto_apply_max_impact
        self.require_approval_impact = set(config.require_approval_impact)

    def needs_approval(self, impact: str) -> bool:
        if impact not in VALID_IMPACT_LEVELS:
            raise GuardrailError(f"非法影响面等级: {impact}")
        rank = VALID_IMPACT_LEVELS.index(impact)
        auto_rank = VALID_IMPACT_LEVELS.index(self.auto_apply_max_impact)
        return impact in self.require_approval_impact or rank > auto_rank


def build_guardrails(
    config: GuardrailsConfig,
    source_root: str | Path,
    output_root: str | Path,
) -> tuple[PathGuard, ToolRegistry, ApprovalPolicy]:
    """集中构造护栏组件，方便主循环注入。"""
    return (
        PathGuard(source_root, output_root),
        ToolRegistry(config.allowed_tools),
        ApprovalPolicy(config),
    )
