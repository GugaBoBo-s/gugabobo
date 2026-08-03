from __future__ import annotations

from dataclasses import dataclass

from gugabobo.config import Settings, get_settings
from gugabobo.core.persona import Persona
from gugabobo.infra.litellm_client import LiteLLMRequest, chat_response_data


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str
    # Raw OpenAI-format assistant message (present when the model asked to call
    # tools). None on a plain text answer. The tool loop appends this verbatim.
    message: dict[str, object] | None = None
    tool_calls: list[dict[str, object]] | None = None


def _build_user_content(text: str, images: list[str]) -> object:
    if not images:
        return text
    parts: list[dict[str, object]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for image in images:
        parts.append({"type": "image_url", "image_url": {"url": image}})
    return parts


class LiteLLMClient:
    provider_name = "openai-compatible"
    litellm_provider = "openai"
    api_key_setting = "the selected provider API key"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key(self) -> str:
        raise NotImplementedError

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    @property
    def model(self) -> str:
        raise NotImplementedError

    def chat(
        self,
        text: str,
        persona: Persona,
        history: list[dict[str, str]] | None = None,
        system_context: list[str] | None = None,
        images: list[str] | None = None,
    ) -> LLMResult:
        if not self.configured:
            raise RuntimeError(
                f"{self.provider_name} API key is not configured; set {self.api_key_setting}"
            )
        messages = self.build_messages(
            text, persona, history or [], system_context or [], images or []
        )
        response = self._request().completion(messages, temperature=0.7)
        content, model, message, tool_calls = chat_response_data(response, self.model)
        return LLMResult(content, model, message, tool_calls)

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError(
                f"{self.provider_name} API key is not configured; set {self.api_key_setting}"
            )
        result = self._request().completion(list(messages), temperature)
        content, _, _, _ = chat_response_data(result, self.model)
        return content

    def build_messages(
        self,
        text: str,
        persona: Persona,
        history: list[dict[str, str]],
        system_context: list[str],
        images: list[str],
    ) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = [
            {"role": "system", "content": persona.system_summary()}
        ]
        for content in system_context:
            if content.strip():
                messages.append({"role": "system", "content": content})
        messages.extend(history)
        messages.append({"role": "user", "content": _build_user_content(text, images)})
        return messages

    def complete_messages(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        temperature: float = 0.7,
    ) -> LLMResult:
        # Low-level chat-completions call over a full message list. Supports the
        # OpenAI `tools` param so callers can run a tool-calling loop; when the
        # model wants to call tools, finish_reason is "tool_calls" and the raw
        # assistant message (with tool_calls) is returned for the loop to append.
        if not self.configured:
            raise RuntimeError(
                f"{self.provider_name} API key is not configured; set {self.api_key_setting}"
            )
        response = self._request().completion(messages, temperature, tools)
        content, model, message, tool_calls = chat_response_data(response, self.model)
        return LLMResult(
            content=content,
            model=model,
            message=message,
            tool_calls=tool_calls,
        )

    def _request(self) -> LiteLLMRequest:
        return LiteLLMRequest(
            provider=self.litellm_provider,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.settings.llm_timeout_seconds,
        )


class MoonshotClient(LiteLLMClient):
    provider_name = "moonshot"
    api_key_setting = "GUGABOBO_MOONSHOT_API_KEY"

    @property
    def api_key(self) -> str:
        return self.settings.moonshot_api_key

    @property
    def base_url(self) -> str:
        return self.settings.moonshot_base_url

    @property
    def model(self) -> str:
        return self.settings.moonshot_model


class DeepSeekClient(LiteLLMClient):
    provider_name = "deepseek"
    litellm_provider = "deepseek"
    api_key_setting = "GUGABOBO_DEEPSEEK_API_KEY"

    @property
    def api_key(self) -> str:
        return self.settings.deepseek_api_key

    @property
    def base_url(self) -> str:
        return self.settings.deepseek_base_url

    @property
    def model(self) -> str:
        return self.settings.deepseek_model


class OpenAIClient(LiteLLMClient):
    provider_name = "openai"
    api_key_setting = "GUGABOBO_OPENAI_API_KEY"

    @property
    def api_key(self) -> str:
        return self.settings.openai_api_key

    @property
    def base_url(self) -> str:
        return self.settings.openai_base_url

    @property
    def model(self) -> str:
        return self.settings.openai_model


def build_llm_client(settings: Settings | None = None) -> LiteLLMClient:
    resolved_settings = settings or get_settings()
    if resolved_settings.llm_provider == "openai":
        return OpenAIClient(resolved_settings)
    if resolved_settings.llm_provider == "deepseek":
        return DeepSeekClient(resolved_settings)
    return MoonshotClient(resolved_settings)
