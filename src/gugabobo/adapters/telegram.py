from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gugabobo.core.channel import ChannelContext


@dataclass(frozen=True)
class TelegramMessageEvent:
    update_id: str
    message_id: str
    chat_id: str
    chat_type: str
    user_id: str
    text: str
    username: str | None = None
    raw_message: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TelegramMessageEvent:
        message = payload.get("message") or payload.get("edited_message") or {}
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = str(chat.get("id", ""))
        user_id = str(user.get("id", chat_id))
        return cls(
            update_id=str(payload.get("update_id", "")),
            message_id=str(message.get("message_id", "")),
            chat_id=chat_id,
            chat_type=str(chat.get("type", "")),
            user_id=user_id,
            text=str(message.get("text", "")).strip(),
            username=str(user["username"]) if user.get("username") is not None else None,
            raw_message=message,
        )

    @property
    def channel_type(self) -> str:
        if self.chat_type == "private":
            return "private"
        if self.chat_type in {"group", "supergroup"}:
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
    def conversation_id(self) -> str:
        if self.channel_type == "group":
            return f"telegram:group:{self.chat_id}"
        return f"telegram:user:{self.user_id}"

    def mentions_bot(self, bot_username: str) -> bool:
        if not bot_username or not self.text:
            return False
        normalized_username = bot_username.lstrip("@").lower()
        return f"@{normalized_username}" in self.text.lower()

    def should_reply(self, group_wake_words: list[str], bot_username: str = "") -> bool:
        if not self.text:
            return False
        if self.channel_type == "private":
            return True
        if self.channel_type != "group":
            return False
        text = self.text.lower()
        return self.mentions_bot(bot_username) or any(
            text.startswith(word.lower()) for word in group_wake_words
        )

    def to_channel_context(
        self,
        owner_ids: set[str] | None = None,
        group_wake_words: list[str] | None = None,
        bot_username: str = "",
    ) -> ChannelContext:
        owner_id_set = owner_ids or set()
        wake_words = group_wake_words or []
        return ChannelContext(
            platform="telegram",
            channel_type=self.channel_type,
            source=self.source,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            group_id=self.chat_id if self.channel_type == "group" else None,
            chat_id=self.chat_id,
            is_owner=self.user_id in owner_id_set,
            is_wake_triggered=self.should_reply(wake_words, bot_username),
            raw_event_id=self.update_id,
            metadata={
                "message_id": self.message_id,
                "chat_type": self.chat_type,
                "username": self.username,
            },
        )
