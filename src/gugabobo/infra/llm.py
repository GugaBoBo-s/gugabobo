from __future__ import annotations

from dataclasses import dataclass

import httpx

from gugabobo.config import Settings, get_settings
from gugabobo.core.persona import Persona


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str


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

    def chat(self, text: str, persona: Persona) -> LLMResult:
        if not self.configured:
            raise RuntimeError(f"{self.provider_name} API key is not configured")
        response = self._post_chat_completion(text, persona)
        choice = response["choices"][0]
        content = choice["message"]["content"]
        return LLMResult(content=str(content).strip(), model=str(response.get("model", "")))

    def _post_chat_completion(self, text: str, persona: Persona) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": persona.system_summary()},
                {"role": "user", "content": text},
            ],
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


def build_llm_client(settings: Settings | None = None) -> OpenAICompatibleClient:
    resolved_settings = settings or get_settings()
    if resolved_settings.llm_provider == "deepseek":
        return DeepSeekClient(resolved_settings)
    return MoonshotClient(resolved_settings)
