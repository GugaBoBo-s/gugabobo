from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from litellm.exceptions import Timeout as LiteLLMTimeout

from gugabobo.config import Settings, get_settings
from gugabobo.infra.llm import AgentRuntime


OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class CodeModelResult(Generic[OutputT]):
    content: OutputT
    provider: str
    model: str


class CodeModelClient(Protocol):
    provider_name: str
    model: str

    @property
    def configured(self) -> bool: ...

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        output_type: type[OutputT] | type[str] = str,
    ) -> OutputT | str: ...


class PydanticCodeAgent(AgentRuntime):
    def __init__(
        self,
        settings: Settings,
        provider_name: str,
        litellm_provider: str,
        api_key: str,
        api_key_setting: str,
        base_url: str,
        model: str,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(settings)
        self.provider_name = provider_name
        self.litellm_provider = litellm_provider
        self.api_key_setting = api_key_setting
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model
        self._max_tokens = max_tokens

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def request_timeout(self) -> int:
        return self.settings.code_model_timeout_seconds

    @property
    def max_tokens(self) -> int | None:
        return self._max_tokens

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        output_type: type[OutputT] | type[str] = str,
    ) -> OutputT | str:
        return self.run_messages(
            messages,
            output_type=output_type,
            temperature=temperature,
        ).output


class CodeModelRouter:
    def __init__(self, clients: list[CodeModelClient]) -> None:
        if not clients:
            raise ValueError("at least one code model client is required")
        self.clients = clients

    @property
    def configured(self) -> bool:
        return self.clients[0].configured

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        result = self.complete_with_metadata(messages, temperature)
        return str(result.content)

    def complete_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        output_type: type[OutputT] | type[str] = str,
    ) -> CodeModelResult[OutputT | str]:
        for index, client in enumerate(self.clients):
            if not client.configured:
                setting = getattr(client, "api_key_setting", "its configured API key")
                raise RuntimeError(
                    f"{client.provider_name} code model is not configured; set {setting}"
                )
            try:
                content = client.complete(messages, temperature, output_type)
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
            PydanticCodeAgent(
                resolved,
                "claude",
                "anthropic",
                resolved.claude_auth_token,
                "GUGABOBO_CLAUDE_AUTH_TOKEN",
                claude_base_url,
                resolved.code_claude_model,
                max_tokens=8192,
            ),
            PydanticCodeAgent(
                resolved,
                "openai",
                "openai",
                resolved.openai_api_key,
                "GUGABOBO_OPENAI_API_KEY",
                resolved.openai_base_url,
                resolved.code_openai_model,
            ),
            PydanticCodeAgent(
                resolved,
                "deepseek",
                "deepseek",
                resolved.deepseek_api_key,
                "GUGABOBO_DEEPSEEK_API_KEY",
                resolved.deepseek_base_url,
                resolved.code_deepseek_model,
            ),
        ]
    )
