from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
        if self.raw_message:
            return self.raw_message.strip()
        if isinstance(self.message, str):
            return self.message.strip()
        if isinstance(self.message, list):
            return "".join(
                str(segment.get("data", {}).get("text", ""))
                for segment in self.message
                if segment.get("type") == "text"
            ).strip()
        return ""

    def mentions_self(self) -> bool:
        if not self.self_id or not isinstance(self.message, list):
            return False
        for segment in self.message:
            if segment.get("type") != "at":
                continue
            if str(segment.get("data", {}).get("qq", "")) == self.self_id:
                return True
        return False


def should_reply_to_event(event: OneBotMessageEvent, group_wake_words: list[str]) -> bool:
    if event.post_type != "message":
        return False
    if event.message_type == "private":
        return True
    if event.message_type != "group":
        return False
    text = event.text_content().lower()
    return event.mentions_self() or any(text.startswith(word.lower()) for word in group_wake_words)
