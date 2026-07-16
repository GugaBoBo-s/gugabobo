from __future__ import annotations

import httpx

from gugabobo.config import get_settings
from gugabobo.infra.images import bytes_to_data_uri
from gugabobo.infra.logs import get_logger
from gugabobo.infra.redaction import redact_sensitive


class TelegramClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: httpx.Client | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token)

    @property
    def base_url(self) -> str:
        if not self.configured:
            raise RuntimeError("Telegram bot token is not configured")
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    @property
    def _proxy(self) -> str | None:
        return self.settings.telegram_proxy or None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(proxy=self._proxy, follow_redirects=True)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def call(
        self,
        method: str,
        payload: dict[str, object] | None = None,
        timeout: float = 35.0,
    ) -> dict[str, object]:
        url = f"{self.base_url}/{method}"
        try:
            response = self.client.post(url, json=payload or {}, timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as error:
            detail = redact_sensitive(error, (self.settings.telegram_bot_token,))
            raise RuntimeError(f"Telegram API {method} failed: {detail}") from None
        if not data.get("ok"):
            detail = redact_sensitive(data, (self.settings.telegram_bot_token,))
            raise RuntimeError(f"Telegram API {method} failed: {detail}")
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
        data = self.call("getUpdates", payload, timeout=timeout + 15)
        result = data.get("result", [])
        if not isinstance(result, list):
            return []
        return [dict(item) for item in result if isinstance(item, dict)]

    def get_me(self) -> dict[str, object]:
        data = self.call("getMe")
        result = data.get("result", {})
        return dict(result) if isinstance(result, dict) else {}

    def send_message(self, chat_id: str, text: str) -> None:
        chunks = _split_message(text)
        for chunk in chunks:
            self.call("sendMessage", {"chat_id": chat_id, "text": chunk})

    def _download_file(self, file_id: str, timeout: float = 20.0) -> bytes | None:
        try:
            data = self.call("getFile", {"file_id": file_id})
            file_path = str(data.get("result", {}).get("file_path", ""))
            if not file_path:
                return None
            token = self.settings.telegram_bot_token
            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            response = self.client.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except Exception as exc:
            detail = redact_sensitive(exc, (self.settings.telegram_bot_token,))
            get_logger().warning("telegram file download failed file_id=%s error=%s", file_id, detail)
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


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    return chunks
