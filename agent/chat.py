from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.config import AppConfig
from agent.guardrails import GuardrailError, PathGuard
from agent.llm import LLMClient, LLMError, parse_json_object
from migration.registry import get_profiles

MAX_ATTEMPTS = 3

UNSUPPORTED_FRAMEWORKS = ("django", "flask")


def build_intent_prompt() -> str:
    """根据档案定义生成意图解析提示。"""
    profile_lines = [
        (
            f"- {name}: {profile.description}；"
            f"scopes={profile.scopes}；keywords={profile.keywords}"
        )
        for name, profile in get_profiles().items()
    ]
    return (
        "你是迁移目标解析器。用户会描述迁移目标，请提取为 JSON："
        '{"profile": "档案名", "scope": "范围", '
        '"needs_more_info": "一句话说明缺少什么，若无则为空字符串"}。\n'
        "只能使用以下已支持档案：\n"
        + "\n".join(profile_lines)
        + "\n不要输出其他内容。"
    )


@dataclass
class ChatResult:
    profile: str
    scope: str
    source: str
    output: str


class ChatSession:
    """对话引导模式：确认迁移目标、路径与范围，最后汇总确认。"""

    def __init__(
        self,
        config: AppConfig,
        llm: LLMClient | None = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.profile = config.migration.profile
        self.scope = config.migration.scope
        self.source: Path | None = None
        self.output: Path | None = None

    def run(self) -> ChatResult:
        self._resolve_goal()
        self._resolve_paths()
        self._confirm()
        return ChatResult(
            profile=self.profile,
            scope=self.scope,
            source=str(self.source),
            output=str(self.output),
        )

    def _resolve_goal(self) -> None:
        for _ in range(MAX_ATTEMPTS):
            answer = input("这次迁移的目标是什么？\n> ").strip()
            intent = self._extract_intent(answer)
            if self._validate_intent(intent):
                self.profile = intent["profile"]
                self.scope = intent["scope"]
                return
            message = (
                intent.get("needs_more_info")
                or "未识别到有效的迁移目标，请重新描述。"
            )
            print(message)

        raise RuntimeError("连续 3 次未识别迁移目标")

    def _extract_intent(self, answer: str) -> dict:
        if self.llm is None:
            return _keyword_intent(answer)
        messages = [
            {"role": "system", "content": build_intent_prompt()},
            {"role": "user", "content": answer},
        ]
        try:
            raw = self.llm.complete(messages, max_tokens=512, json_mode=True)
            data = parse_json_object(raw)
        except LLMError:
            return _keyword_intent(answer)
        return data if isinstance(data, dict) else _keyword_intent(answer)

    @staticmethod
    def _validate_intent(intent: dict) -> bool:
        profiles = get_profiles()
        profile = intent.get("profile")
        if profile not in profiles:
            return False
        return intent.get("scope") in profiles[profile].scopes

    def _resolve_paths(self) -> None:
        for _ in range(MAX_ATTEMPTS):
            source = input("请输入待迁移项目路径: ").strip()
            output = input("请输入迁移输出路径: ").strip()
            if not Path(source).is_dir():
                print("输入项目不存在或不是目录，请重新输入。")
                continue
            try:
                PathGuard(source, output)
            except GuardrailError as exc:
                print(f"路径不合法: {exc}")
                continue
            self.source = Path(source)
            self.output = Path(output)
            return

        raise RuntimeError("连续 3 次路径输入无效")

    def _confirm(self) -> None:
        print("迁移方案确认：")
        print(f"  档案: {self.profile}（{self.scope}）")
        print(f"  输入: {self.source}")
        print(f"  输出: {self.output}")
        answer = input("确认开始吗？[y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            raise RuntimeError("用户取消确认")


def _keyword_intent(answer: str) -> dict:
    text = answer.lower()
    profiles = get_profiles()
    if any(keyword in text for keyword in UNSUPPORTED_FRAMEWORKS):
        supported = "、".join(profiles)
        return {
            "profile": "unknown",
            "scope": "",
            "needs_more_info": f"暂不支持该框架档案，可选 {supported}",
        }

    for name, profile in profiles.items():
        if not any(keyword.lower() in text for keyword in profile.keywords):
            continue
        scope = profile.default_scope or profile.scopes[0]
        if "deprecated_api" in profile.scopes and any(
            keyword in text for keyword in ("api", "废弃")
        ):
            scope = "deprecated_api"
        return {
            "profile": name,
            "scope": scope,
            "needs_more_info": "",
        }

    supported = "、".join(profiles)
    return {
        "profile": "unknown",
        "scope": "",
        "needs_more_info": f"未识别到支持的迁移目标，可选 {supported}",
    }
