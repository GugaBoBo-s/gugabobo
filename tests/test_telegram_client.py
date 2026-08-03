import asyncio
from io import BytesIO

import pytest
from aiogram.types import User

from gugabobo.config import get_settings
from gugabobo.infra.telegram_client import TelegramClient


class FakeSession:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class ExplodingBot:
    def __init__(self, message):
        self.message = message
        self.session = FakeSession()

    async def get_me(self):
        raise RuntimeError(f"request failed: {self.message}")


class RecordingBot:
    def __init__(self):
        self.session = FakeSession()
        self.messages = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )

    async def set_my_commands(self, commands):
        self.commands = commands

    async def get_me(self):
        return User(id=10001, is_bot=True, first_name="gugabobo", username="gugabobo_bot")

    async def download(self, file_id, timeout):
        return BytesIO(b"image")


def test_api_errors_redact_bot_token(monkeypatch):
    token = "1234567890:" + "AA" + "a" * 32
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", token)
    get_settings.cache_clear()
    client = TelegramClient()
    bot = ExplodingBot(token)
    client._bot = bot

    async def get_me():
        try:
            await client.get_me()
        finally:
            await client.close()

    with pytest.raises(RuntimeError) as captured:
        asyncio.run(get_me())

    message = str(captured.value)
    assert token not in message
    assert "<redacted>" in message
    assert bot.session.closed is True
    get_settings.cache_clear()


def test_long_messages_are_split_before_sending(monkeypatch):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "1234567890:" + "AA" + "a" * 30)
    get_settings.cache_clear()
    client = TelegramClient()
    bot = RecordingBot()
    client._bot = bot
    message = "x" * 9001

    async def send():
        await client.send_message("10001", message)
        await client.close()

    asyncio.run(send())

    chunks = [item["text"] for item in bot.messages]
    assert len(chunks) == 3
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks) == message
    assert bot.session.closed is True
    get_settings.cache_clear()


def test_get_me_returns_aiogram_model_as_mapping(monkeypatch):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "1234567890:" + "AA" + "a" * 30)
    get_settings.cache_clear()
    client = TelegramClient()
    bot = RecordingBot()
    client._bot = bot

    async def get_me():
        result = await client.get_me()
        await client.close()
        return result

    result = asyncio.run(get_me())

    assert result["id"] == 10001
    assert result["username"] == "gugabobo_bot"
    assert bot.session.closed is True
    get_settings.cache_clear()


def test_files_are_downloaded_through_aiogram(monkeypatch):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "1234567890:" + "AA" + "a" * 30)
    get_settings.cache_clear()
    client = TelegramClient()
    bot = RecordingBot()
    client._bot = bot

    async def download():
        result = await client.file_ids_to_data_uris(["photo-1"])
        await client.close()
        return result

    result = asyncio.run(download())

    assert result == ["data:image/jpeg;base64,aW1hZ2U="]
    assert bot.session.closed is True
    get_settings.cache_clear()


def test_bot_commands_include_community_summary_and_developers(monkeypatch):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "1234567890:" + "AA" + "a" * 30)
    get_settings.cache_clear()
    client = TelegramClient()
    bot = RecordingBot()
    client._bot = bot

    async def set_commands():
        await client.set_commands()
        await client.close()

    asyncio.run(set_commands())

    assert [command.command for command in bot.commands] == [
        "community",
        "fogmoe",
        "summary",
        "developers",
        "github",
    ]
    assert bot.session.closed is True
    get_settings.cache_clear()
