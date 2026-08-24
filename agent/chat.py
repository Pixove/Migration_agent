from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.config import AppConfig
from agent.guardrails import GuardrailError, PathGuard
from agent.llm import LLMClient, LLMError, parse_json_object
from migration.registry import get_profiles

MAX_ATTEMPTS = 3

INTENT_PROMPT = (
    "你是迁移目标解析器。用户会描述迁移目标，请提取为 JSON："
    '{"profile": "py2to3|py3_upgrade", "scope": "syntax|deprecated_api", '
    '"needs_more_info": "一句话说明缺少什么，若无则为空字符串"}。'
    "只能使用已支持的档案，不要输出其他内容。"
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
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": answer},
        ]
        try:
            raw = self.llm.complete(messages, max_tokens=512)
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
    if any(keyword in text for keyword in ("django", "flask", "框架")):
        return {
            "profile": "unknown",
            "scope": "",
            "needs_more_info": "暂不支持框架档案，可选 py2to3 或 py3_upgrade",
        }
    if any(keyword in text for keyword in ("python 2", "py2", "2to3")):
        return {
            "profile": "py2to3",
            "scope": "syntax",
            "needs_more_info": "",
        }
    if any(keyword in text for keyword in ("3.8", "升级", "新版", "python 3")):
        scope = (
            "deprecated_api"
            if any(keyword in text for keyword in ("api", "废弃"))
            else "syntax"
        )
        return {
            "profile": "py3_upgrade",
            "scope": scope,
            "needs_more_info": "",
        }
    return {
        "profile": "unknown",
        "scope": "",
        "needs_more_info": "未识别到支持的迁移目标，请描述目标版本或档案",
    }
