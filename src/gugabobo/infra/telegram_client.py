from __future__ import annotations

import httpx

from gugabobo.config import get_settings
from gugabobo.infra.images import bytes_to_data_uri
from gugabobo.infra.logs import get_logger


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

    def get_me(self) -> dict[str, object]:
        data = self.call("getMe")
        result = data.get("result", {})
        return dict(result) if isinstance(result, dict) else {}

    def send_message(self, chat_id: str, text: str) -> None:
        self.call("sendMessage", {"chat_id": chat_id, "text": text})

    def _download_file(self, file_id: str, timeout: float = 20.0) -> bytes | None:
        # Telegram photos are two-step: getFile returns a file_path, then the
        # file is fetched from the /file/bot<token>/ endpoint. The token stays
        # inside this method and is never logged.
        try:
            data = self.call("getFile", {"file_id": file_id})
            file_path = str(data.get("result", {}).get("file_path", ""))
            if not file_path:
                return None
            token = self.settings.telegram_bot_token
            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as exc:
            get_logger().warning("telegram file download failed file_id=%s error=%s", file_id, exc)
            return None

    def file_ids_to_data_uris(self, file_ids: list[str], timeout: float = 20.0) -> list[str]:
        data_uris: list[str] = []
        for file_id in file_ids:
            content = self._download_file(file_id, timeout=timeout)
            if not content:
                continue
            data_uri = bytes_to_data_uri(content)
            if data_uri:
                data_uris.append(data_uri)
        return data_uris
