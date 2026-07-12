from __future__ import annotations

from dataclasses import dataclass

import httpx

from gugabobo.config import Settings, get_settings
from gugabobo.core.persona import Persona


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str


def _build_user_content(text: str, images: list[str]) -> object:
    if not images:
        return text
    parts: list[dict[str, object]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for image in images:
        parts.append({"type": "image_url", "image_url": {"url": image}})
    return parts


class OpenAICompatibleClient:
    provider_name = "openai-compatible"

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
            raise RuntimeError(f"{self.provider_name} API key is not configured")
        response = self._post_chat_completion(
            text, persona, history or [], system_context or [], images or []
        )
        choice = response["choices"][0]
        content = choice["message"]["content"]
        return LLMResult(content=str(content).strip(), model=str(response.get("model", "")))

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.configured:
            raise RuntimeError(f"{self.provider_name} API key is not configured")
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
        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()

    def _post_chat_completion(
        self,
        text: str,
        persona: Persona,
        history: list[dict[str, str]],
        system_context: list[str],
        images: list[str],
    ) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = [{"role": "system", "content": persona.system_summary()}]
        for content in system_context:
            if content.strip():
                messages.append({"role": "system", "content": content})
        messages.extend(history)
        messages.append({"role": "user", "content": _build_user_content(text, images)})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }
        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()


class MoonshotClient(OpenAICompatibleClient):
    provider_name = "moonshot"

    @property
    def api_key(self) -> str:
        return self.settings.moonshot_api_key

    @property
    def base_url(self) -> str:
        return self.settings.moonshot_base_url

    @property
    def model(self) -> str:
        return self.settings.moonshot_model


class DeepSeekClient(OpenAICompatibleClient):
    provider_name = "deepseek"

    @property
    def api_key(self) -> str:
        return self.settings.deepseek_api_key

    @property
    def base_url(self) -> str:
        return self.settings.deepseek_base_url

    @property
    def model(self) -> str:
        return self.settings.deepseek_model


class OpenAIClient(OpenAICompatibleClient):
    provider_name = "openai"

    @property
    def api_key(self) -> str:
        return self.settings.openai_api_key

    @property
    def base_url(self) -> str:
        return self.settings.openai_base_url

    @property
    def model(self) -> str:
        return self.settings.openai_model


def build_llm_client(settings: Settings | None = None) -> OpenAICompatibleClient:
    resolved_settings = settings or get_settings()
    if resolved_settings.llm_provider == "openai":
        return OpenAIClient(resolved_settings)
    if resolved_settings.llm_provider == "deepseek":
        return DeepSeekClient(resolved_settings)
    return MoonshotClient(resolved_settings)
