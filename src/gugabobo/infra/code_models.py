from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from gugabobo.config import Settings, get_settings


@dataclass(frozen=True)
class CodeModelResult:
    content: str
    provider: str
    model: str


class CodeModelClient(Protocol):
    provider_name: str
    model: str

    @property
    def configured(self) -> bool: ...

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str: ...


class AnthropicCodeClient:
    provider_name = "claude"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.claude_auth_token)

    @property
    def model(self) -> str:
        return self.settings.code_claude_model

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError("Claude code model is not configured")
        system_parts = [item["content"] for item in messages if item["role"] == "system"]
        conversation = [item for item in messages if item["role"] != "system"]
        base_url = self.settings.claude_base_url or "https://api.anthropic.com"
        base_url = base_url.rstrip("/")
        url = f"{base_url}/messages" if base_url.endswith("/v1") else f"{base_url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.settings.claude_auth_token}",
            "x-api-key": self.settings.claude_auth_token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload: dict[str, object] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": conversation,
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        with httpx.Client(timeout=self.settings.code_model_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        blocks = data.get("content", [])
        return "\n".join(
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()


class OpenAICompatibleCodeClient:
    def __init__(
        self,
        provider_name: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int,
    ) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError(f"{self.provider_name} code model is not configured")
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()


class OpenAIResponsesCodeClient(OpenAICompatibleCodeClient):
    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError("openai code model is not configured")
        url = f"{self.base_url.rstrip('/')}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "input": messages}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        if data.get("output_text"):
            return str(data["output_text"]).strip()
        parts: list[str] = []
        for output in data.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    parts.append(str(content.get("text", "")))
        if not parts:
            raise ValueError("OpenAI response did not contain output text")
        return "\n".join(parts).strip()


class CodeModelRouter:
    def __init__(self, clients: list[CodeModelClient]) -> None:
        if not clients:
            raise ValueError("at least one code model client is required")
        self.clients = clients

    @property
    def configured(self) -> bool:
        return self.clients[0].configured

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        return self.complete_with_metadata(messages, temperature).content

    def complete_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> CodeModelResult:
        for index, client in enumerate(self.clients):
            if not client.configured:
                raise RuntimeError(f"{client.provider_name} code model is not configured")
            try:
                content = client.complete(messages, temperature)
                return CodeModelResult(content, client.provider_name, client.model)
            except Exception as error:
                if not _is_timeout(error) or index == len(self.clients) - 1:
                    raise
        raise RuntimeError("code model chain produced no result")


def _is_timeout(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {
        408,
        504,
        524,
    }


def build_code_model_router(settings: Settings | None = None) -> CodeModelRouter:
    resolved = settings or get_settings()
    return CodeModelRouter(
        [
            AnthropicCodeClient(resolved),
            OpenAIResponsesCodeClient(
                "openai",
                resolved.openai_api_key,
                resolved.openai_base_url,
                resolved.code_openai_model,
                resolved.code_model_timeout_seconds,
            ),
            OpenAICompatibleCodeClient(
                "deepseek",
                resolved.deepseek_api_key,
                resolved.deepseek_base_url,
                resolved.code_deepseek_model,
                resolved.code_model_timeout_seconds,
            ),
        ]
    )
