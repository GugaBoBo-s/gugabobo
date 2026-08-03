from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import Message, Update

from gugabobo.core.channel import ChannelContext


@dataclass(frozen=True)
class TelegramIncomingMessage:
    update_id: str
    message: Message

    @classmethod
    def from_update(cls, update: Update) -> TelegramIncomingMessage | None:
        message = update.message or update.edited_message
        if message is None:
            return None
        return cls(update_id=str(update.update_id), message=message)

    @property
    def text(self) -> str:
        return (self.message.text or self.message.caption or "").strip()

    @property
    def user_id(self) -> str:
        user = self.message.from_user
        return str(user.id if user else self.message.chat.id)

    @property
    def chat_id(self) -> str:
        return str(self.message.chat.id)

    @property
    def channel_type(self) -> str:
        chat_type = self.message.chat.type
        if chat_type == "private":
            return "private"
        if chat_type in {"group", "supergroup"}:
            return "group"
        return "unknown"

    @property
    def source(self) -> str:
        if self.channel_type == "private":
            return "telegram_private"
        if self.channel_type == "group":
            return "telegram_group"
        return "telegram"

    @property
    def photo_file_ids(self) -> tuple[str, ...]:
        if not self.message.photo:
            return ()
        return (self.message.photo[-1].file_id,)

    def has_content(self) -> bool:
        return bool(self.text or self.photo_file_ids)

    def to_channel_context(
        self,
        owner_ids: set[str],
        group_wake_words: list[str],
        bot_username: str,
    ) -> ChannelContext:
        username = self.message.from_user.username if self.message.from_user else None
        return ChannelContext(
            platform="telegram",
            channel_type=self.channel_type,
            source=self.source,
            user_id=self.user_id,
            conversation_id=(
                f"telegram:group:{self.chat_id}"
                if self.channel_type == "group"
                else f"telegram:user:{self.user_id}"
            ),
            group_id=self.chat_id if self.channel_type == "group" else None,
            chat_id=self.chat_id,
            is_owner=self.user_id in owner_ids,
            is_wake_triggered=self._should_reply(group_wake_words, bot_username),
            raw_event_id=self.update_id,
            metadata={
                "message_id": str(self.message.message_id),
                "chat_type": str(self.message.chat.type),
                "username": username,
            },
        )

    def _should_reply(self, group_wake_words: list[str], bot_username: str) -> bool:
        if not self.has_content():
            return False
        if self.channel_type == "private":
            return True
        if self.channel_type != "group":
            return False
        text = self.text.casefold()
        normalized_username = bot_username.lstrip("@").casefold()
        mentioned = bool(normalized_username and f"@{normalized_username}" in text)
        awakened = any(text.startswith(word.casefold()) for word in group_wake_words)
        return mentioned or awakened
