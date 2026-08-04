from __future__ import annotations

from io import BytesIO

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand, InlineKeyboardMarkup

from gugabobo.config import get_settings
from gugabobo.infra.images import bytes_to_data_uri
from gugabobo.infra.logs import get_logger
from gugabobo.infra.redaction import redact_sensitive

class TelegramClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._bot: Bot | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token)

    @property
    def bot(self) -> Bot:
        if not self.configured:
            raise RuntimeError("Telegram bot token is not configured")
        if self._bot is None:
            session = AiohttpSession(proxy=self.settings.telegram_proxy or None)
            self._bot = Bot(token=self.settings.telegram_bot_token, session=session)
        return self._bot

    async def close(self) -> None:
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None

    async def get_me(self) -> dict[str, object]:
        try:
            result = await self.bot.get_me()
            return result.model_dump(mode="json", exclude_none=True)
        except Exception as error:
            self._raise_api_error("getMe", error)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        try:
            for chunk in _split_message(text):
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_markup=reply_markup,
                )
                reply_markup = None
        except Exception as error:
            self._raise_api_error("sendMessage", error)

    async def set_commands(self) -> None:
        try:
            await self.bot.set_my_commands(
                [
                    BotCommand(command="community", description="查看 Telegram 社区入口"),
                    BotCommand(command="fogmoe", description="打开雾萌与 FOGMOE 入口"),
                    BotCommand(command="summary", description="使用群组总结机器人"),
                    BotCommand(command="developers", description="查看项目开发者账号"),
                    BotCommand(command="github", description="查看关联 GitHub 账号"),
                ]
            )
        except Exception as error:
            self._raise_api_error("setMyCommands", error)

    async def file_ids_to_data_uris(
        self,
        file_ids: list[str],
        timeout: float = 20.0,
    ) -> list[str]:
        data_uris: list[str] = []
        for file_id in file_ids:
            try:
                destination = await self.bot.download(file_id, timeout=int(timeout))
                content = _read_download(destination)
                data_uri = bytes_to_data_uri(content) if content else None
                if data_uri:
                    data_uris.append(data_uri)
            except Exception as error:
                detail = redact_sensitive(error, (self.settings.telegram_bot_token,))
                get_logger().warning(
                    "telegram file download failed file_id=%s error=%s",
                    file_id,
                    detail,
                )
        return data_uris

    def _raise_api_error(self, method: str, error: Exception) -> None:
        detail = redact_sensitive(error, (self.settings.telegram_bot_token,))
        raise RuntimeError(f"Telegram API {method} failed: {detail}") from None


def _read_download(destination: object) -> bytes | None:
    if isinstance(destination, BytesIO):
        return destination.getvalue()
    read = getattr(destination, "read", None)
    if not callable(read):
        return None
    content = read()
    return content if isinstance(content, bytes) else None


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
