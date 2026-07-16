import pytest

from gugabobo.config import get_settings
from gugabobo.infra.telegram_client import TelegramClient


class ExplodingHttpClient:
    def __init__(self, message):
        self.message = message

    def post(self, url, json, timeout):
        raise RuntimeError(f"request failed: {url} {self.message}")


def test_api_errors_redact_bot_token(monkeypatch):
    token = "1234567890:" + "AA" + "a" * 32
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", token)
    get_settings.cache_clear()
    client = TelegramClient()
    client._client = ExplodingHttpClient(token)

    with pytest.raises(RuntimeError) as captured:
        client.get_me()

    message = str(captured.value)
    assert token not in message
    assert "<redacted>" in message
    get_settings.cache_clear()


def test_long_messages_are_split_before_sending(monkeypatch):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "1234567890:" + "AA" + "a" * 30)
    get_settings.cache_clear()
    client = TelegramClient()
    calls = []
    client.call = lambda method, payload: calls.append((method, payload)) or {"ok": True}
    message = "x" * 9001

    client.send_message("10001", message)

    chunks = [payload["text"] for _, payload in calls]
    assert len(chunks) == 3
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks) == message
    get_settings.cache_clear()
