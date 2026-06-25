from __future__ import annotations

from dataclasses import dataclass

import httpx

from gugabobo.config import Settings, get_settings
from gugabobo.core.persona import Persona


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str


class MoonshotClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.moonshot_api_key)

    def chat(self, text: str, persona: Persona) -> LLMResult:
        if not self.configured:
            raise RuntimeError("Moonshot API key is not configured")
        response = self._post_chat_completion(text, persona)
        choice = response["choices"][0]
        content = choice["message"]["content"]
        return LLMResult(content=str(content).strip(), model=str(response.get("model", "")))

    def _post_chat_completion(self, text: str, persona: Persona) -> dict[str, object]:
        url = f"{self.settings.moonshot_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.moonshot_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.moonshot_model,
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
