from __future__ import annotations

import httpx

from gugabobo.config import get_settings


class TelegramClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token)

    def send_message(self, chat_id: str, text: str) -> None:
        if not self.configured:
            raise RuntimeError("Telegram bot token is not configured")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
