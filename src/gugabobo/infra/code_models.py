from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from litellm.exceptions import Timeout as LiteLLMTimeout

from gugabobo.config import Settings, get_settings
from gugabobo.infra.litellm_client import (
    LiteLLMRequest,
    chat_response_data,
    responses_output_text,
)


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


class LiteLLMCodeClient:
    def __init__(
        self,
        provider_name: str,
        litellm_provider: str,
        api_key: str,
        api_key_setting: str,
        base_url: str,
        model: str,
        timeout: int,
        max_tokens: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.litellm_provider = litellm_provider
        self.api_key = api_key
        self.api_key_setting = api_key_setting
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.extra_headers = extra_headers

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError(
                f"{self.provider_name} code model is not configured; set {self.api_key_setting}"
            )
        response = self._request().completion(
            list(messages),
            temperature,
            max_tokens=self.max_tokens,
        )
        content, _, _, _ = chat_response_data(response, self.model)
        return content

    def _request(self) -> LiteLLMRequest:
        return LiteLLMRequest(
            provider=self.litellm_provider,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            extra_headers=self.extra_headers,
        )


class OpenAIResponsesCodeClient(LiteLLMCodeClient):
    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError(
                f"{self.provider_name} code model is not configured; set {self.api_key_setting}"
            )
        return responses_output_text(self._request().responses(messages))


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
                setting = getattr(client, "api_key_setting", "its configured API key")
                raise RuntimeError(
                    f"{client.provider_name} code model is not configured; set {setting}"
                )
            try:
                content = client.complete(messages, temperature)
                return CodeModelResult(content, client.provider_name, client.model)
            except Exception as error:
                if not _is_timeout(error) or index == len(self.clients) - 1:
                    raise
        raise RuntimeError("code model chain produced no result")


def _is_timeout(error: Exception) -> bool:
    if isinstance(error, (LiteLLMTimeout, TimeoutError)):
        return True
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    return status_code in {408, 504, 524}


def build_code_model_router(settings: Settings | None = None) -> CodeModelRouter:
    resolved = settings or get_settings()
    claude_base_url = (resolved.claude_base_url or "https://api.anthropic.com").rstrip("/")
    if claude_base_url.endswith("/v1"):
        claude_base_url = claude_base_url[:-3]
    return CodeModelRouter(
        [
            LiteLLMCodeClient(
                "claude",
                "anthropic",
                resolved.claude_auth_token,
                "GUGABOBO_CLAUDE_AUTH_TOKEN",
                claude_base_url,
                resolved.code_claude_model,
                resolved.code_model_timeout_seconds,
                max_tokens=8192,
                extra_headers={"Authorization": f"Bearer {resolved.claude_auth_token}"},
            ),
            OpenAIResponsesCodeClient(
                "openai",
                "openai",
                resolved.openai_api_key,
                "GUGABOBO_OPENAI_API_KEY",
                resolved.openai_base_url,
                resolved.code_openai_model,
                resolved.code_model_timeout_seconds,
            ),
            LiteLLMCodeClient(
                "deepseek",
                "deepseek",
                resolved.deepseek_api_key,
                "GUGABOBO_DEEPSEEK_API_KEY",
                resolved.deepseek_base_url,
                resolved.code_deepseek_model,
                resolved.code_model_timeout_seconds,
            ),
        ]
    )
