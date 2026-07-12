from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from gugabobo.core.channel import ChannelContext


@dataclass(frozen=True)
class OneBotMessageEvent:
    post_type: str
    message_type: str
    user_id: str
    raw_message: str
    message: Any
    self_id: str | None = None
    group_id: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> OneBotMessageEvent:
        return cls(
            post_type=str(payload.get("post_type", "")),
            message_type=str(payload.get("message_type", "")),
            user_id=str(payload.get("user_id", "")),
            raw_message=str(payload.get("raw_message", "")),
            message=payload.get("message", ""),
            self_id=str(payload["self_id"]) if payload.get("self_id") is not None else None,
            group_id=str(payload["group_id"]) if payload.get("group_id") is not None else None,
        )

    @property
    def source(self) -> str:
        if self.message_type == "group":
            return "qq_group"
        if self.message_type == "private":
            return "qq_private"
        return "qq"

    @property
    def conversation_id(self) -> str:
        if self.group_id:
            return f"qq:group:{self.group_id}"
        return f"qq:user:{self.user_id}"

    def text_content(self) -> str:
        if isinstance(self.message, list):
            text = "".join(
                str(segment.get("data", {}).get("text", ""))
                for segment in self.message
                if segment.get("type") == "text"
            ).strip()
            if text:
                return text
        if self.raw_message:
            return _strip_cq_codes(self.raw_message).strip()
        if isinstance(self.message, str):
            return _strip_cq_codes(self.message).strip()
        return ""

    def image_urls(self) -> list[str]:
        urls: list[str] = []
        if isinstance(self.message, list):
            for segment in self.message:
                if segment.get("type") != "image":
                    continue
                data = segment.get("data", {})
                url = data.get("url") or data.get("file")
                if url:
                    urls.append(str(url))
        return urls

    def has_content(self) -> bool:
        return bool(self.text_content() or self.image_urls())

    def mentions_self(self) -> bool:
        if not self.self_id or not isinstance(self.message, list):
            return False
        for segment in self.message:
            if segment.get("type") != "at":
                continue
            if str(segment.get("data", {}).get("qq", "")) == self.self_id:
                return True
        return False

    def to_channel_context(
        self,
        owner_ids: set[str] | None = None,
        group_wake_words: list[str] | None = None,
    ) -> ChannelContext:
        owner_id_set = owner_ids or set()
        wake_words = group_wake_words or []
        channel_type = "unknown"
        if self.message_type == "group":
            channel_type = "group"
        elif self.message_type == "private":
            channel_type = "private"
        return ChannelContext(
            platform="qq",
            channel_type=channel_type,
            source=self.source,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            group_id=self.group_id,
            chat_id=self.group_id or self.user_id,
            is_owner=self.user_id in owner_id_set,
            is_wake_triggered=should_reply_to_event(self, wake_words),
            metadata={"self_id": self.self_id, "message_type": self.message_type},
        )


def _strip_cq_codes(text: str) -> str:
    return re.sub(r"\[CQ:[^\]]*\]", "", text)


def should_reply_to_event(event: OneBotMessageEvent, group_wake_words: list[str]) -> bool:
    if event.post_type != "message":
        return False
    if event.message_type == "private":
        return True
    if event.message_type != "group":
        return False
    text = event.text_content().lower()
    return event.mentions_self() or any(text.startswith(word.lower()) for word in group_wake_words)
