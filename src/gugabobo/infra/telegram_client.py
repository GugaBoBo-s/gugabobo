from __future__ import annotations

import httpx

from gugabobo.config import get_settings


class TelegramClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token)

    @property
    def base_url(self) -> str:
        if not self.configured:
            raise RuntimeError("Telegram bot token is not configured")
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    def call(self, method: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        url = f"{self.base_url}/{method}"
        with httpx.Client(timeout=35) as client:
            response = client.post(url, json=payload or {})
            response.raise_for_status()
            data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API call failed: {data}")
        return dict(data)

    def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 30,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        payload: dict[str, object] = {
            "timeout": timeout,
            "limit": limit,
            "allowed_updates": ["message", "edited_message"],
        }
        if offset is not None:
            payload["offset"] = offset
        data = self.call("getUpdates", payload)
        result = data.get("result", [])
        if not isinstance(result, list):
            return []
        return [dict(item) for item in result if isinstance(item, dict)]

    def send_message(self, chat_id: str, text: str) -> None:
        self.call("sendMessage", {"chat_id": chat_id, "text": text})
