import pytest

from gugabobo.config import get_settings
from gugabobo.infra.telegram_client import TelegramClient


class ExplodingHttpClient:
    def __init__(self, message):
        self.message = message

    def post(self, url, json, timeout):
        raise RuntimeError(f"request failed: {url} {self.message}")


class StreamResponse:
    def __init__(self, chunks, content_length=0):
        self.chunks = chunks
        self.headers = {"content-length": str(content_length)} if content_length else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield from self.chunks


class StreamingHttpClient:
    def __init__(self, response):
        self.response = response
        self.urls = []

    def stream(self, method, url, timeout):
        self.urls.append((method, url, timeout))
        return self.response


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


def test_document_download_streams_to_bounded_destination(tmp_path, monkeypatch):
    token = "1234567890:" + "AA" + "a" * 30
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", token)
    get_settings.cache_clear()
    client = TelegramClient()
    client.call = lambda method, payload: {
        "ok": True,
        "result": {"file_path": "documents/report.txt"},
    }
    streaming = StreamingHttpClient(StreamResponse([b"hello", b" world"], 11))
    client._client = streaming
    destination = tmp_path / "telegram" / "report.txt"

    result = client.download_file_to("file-id", destination, max_bytes=20, timeout=12)

    assert result is True
    assert destination.read_bytes() == b"hello world"
    assert token in streaming.urls[0][1]
    get_settings.cache_clear()


def test_document_download_removes_partial_file_when_limit_is_exceeded(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "token")
    get_settings.cache_clear()
    client = TelegramClient()
    client.call = lambda method, payload: {
        "ok": True,
        "result": {"file_path": "documents/large.bin"},
    }
    client._client = StreamingHttpClient(StreamResponse([b"12345", b"67890"]))
    destination = tmp_path / "large.bin"

    result = client.download_file_to("file-id", destination, max_bytes=8, timeout=12)

    assert result is False
    assert not destination.exists()
    assert not destination.with_suffix(".bin.part").exists()
    get_settings.cache_clear()
