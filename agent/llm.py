from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from agent.config import LLMConfig, api_key_for


class LLMError(Exception):
    """LLM 调用或响应解析失败时抛出。"""


class LLMClient(ABC):
    """所有模型提供方的统一接口。"""

    name = "base"

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @abstractmethod
    def ping(self) -> bool:
        """检查服务是否可用，不发送完整对话。"""

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """发送对话并返回文本结果。"""

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ) -> dict[str, Any]:
        """发送对话并要求模型返回 JSON，解析失败时抛 LLMError。"""
        raw = self.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return parse_json_object(raw)

    def _timeout(self) -> int:
        return self.config.timeout_seconds


class OpenAICompatibleClient(LLMClient):
    """兼容 OpenAI /chat/completions 协议的服务，包括本地兼容服务。"""

    name = "openai"

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self.base_url = config.openai_base_url.rstrip("/")
        self.model = config.openai_model
        self.api_key = api_key_for(config)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def ping(self) -> bool:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=min(self._timeout(), 15),
            )
            return response.status_code < 500
        except requests.RequestException:
            return False

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            current = dict(payload)
            if json_mode and attempt == 0:
                current["response_format"] = {"type": "json_object"}
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=current,
                    timeout=self._timeout(),
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
        if response is None:
            raise LLMError(
                f"OpenAI 兼容服务请求失败: {last_error}"
            ) from last_error

        if response.status_code != 200:
            raise LLMError(f"OpenAI 兼容服务返回 {response.status_code}: {response.text[:500]}")

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"OpenAI 兼容服务响应格式异常: {data}") from exc


class OllamaClient(LLMClient):
    """本地 Ollama 服务适配。"""

    name = "ollama"

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self.base_url = config.ollama_base_url.rstrip("/")
        self.model = config.ollama_model

    def ping(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=min(self._timeout(), 15))
            return response.status_code == 200
        except requests.RequestException:
            return False

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature if temperature is None else temperature,
                "num_predict": self.config.max_tokens if max_tokens is None else max_tokens,
            },
        }
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            current = dict(payload)
            if json_mode and attempt == 0:
                current["format"] = "json"
            try:
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=current,
                    timeout=self._timeout(),
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
        if response is None:
            raise LLMError(f"Ollama 请求失败: {last_error}") from last_error

        if response.status_code != 200:
            raise LLMError(f"Ollama 返回 {response.status_code}: {response.text[:500]}")

        data = response.json()
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Ollama 响应格式异常: {data}") from exc


def create_llm_client(config: LLMConfig) -> LLMClient:
    """根据配置创建对应的 LLM 客户端。"""
    if config.provider == "openai":
        return OpenAICompatibleClient(config)
    if config.provider == "ollama":
        return OllamaClient(config)
    raise LLMError(f"不支持的 provider: {config.provider}")


def parse_json_object(raw: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象，容忍代码围栏与前后噪音。"""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("顶层不是 JSON 对象")
        return data
    except (json.JSONDecodeError, ValueError):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        raise LLMError(f"无法从模型输出中解析 JSON: {raw[:500]}")
