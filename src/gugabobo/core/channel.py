from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Platform = Literal["cli", "api", "qq", "telegram", "github", "web", "unknown"]
ChannelType = Literal["private", "group", "local", "webhook", "unknown"]


@dataclass(frozen=True)
class ChannelContext:
    platform: Platform
    channel_type: ChannelType
    source: str
    user_id: str
    conversation_id: str
    person_id: int | None = None
    group_id: str | None = None
    chat_id: str | None = None
    is_owner: bool = False
    is_wake_triggered: bool = False
    raw_event_id: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def local(cls, user_id: str = "local", conversation_id: str | None = None) -> ChannelContext:
        return cls(
            platform="cli",
            channel_type="local",
            source="cli",
            user_id=user_id,
            conversation_id=conversation_id or f"cli:{user_id}",
            is_owner=True,
            is_wake_triggered=True,
        )

    @classmethod
    def api(cls, user_id: str = "api", conversation_id: str | None = None) -> ChannelContext:
        return cls(
            platform="api",
            channel_type="webhook",
            source="api",
            user_id=user_id,
            conversation_id=conversation_id or f"api:{user_id}",
            is_wake_triggered=True,
        )

    @property
    def is_group(self) -> bool:
        return self.channel_type == "group"

    @property
    def is_direct_message(self) -> bool:
        return self.channel_type in {"private", "local"}
