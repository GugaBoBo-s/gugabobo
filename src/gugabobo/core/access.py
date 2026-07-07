from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from gugabobo.core.channel import ChannelContext
from gugabobo.memory.store import MemoryStore

AccessRole = Literal["owner", "trusted", "user", "blocked"]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    role: str
    reason: str = ""


def evaluate_access(context: ChannelContext, store: MemoryStore) -> AccessDecision:
    rule = store.get_access_rule(context.platform, context.user_id)
    if not rule:
        if context.is_owner:
            return AccessDecision(allowed=True, role="owner")
        return AccessDecision(allowed=True, role="user")
    role = str(rule["role"])
    if role == "blocked":
        return AccessDecision(allowed=False, role=role, reason="blocked")
    return AccessDecision(allowed=True, role=role)


def context_with_access_role(
    context: ChannelContext,
    access: AccessDecision,
) -> ChannelContext:
    metadata = dict(context.metadata or {})
    metadata["access_role"] = access.role
    return replace(
        context,
        is_owner=context.is_owner or access.role == "owner",
        metadata=metadata,
    )


def role_can_use_skill(role: str, skill: str) -> bool:
    if role == "owner":
        return True
    if role == "trusted":
        return skill in {"chat", "feedback", "memory"}
    return skill == "chat"


def context_access_role(context: ChannelContext) -> str:
    metadata = context.metadata or {}
    role = metadata.get("access_role")
    if isinstance(role, str) and role:
        return role
    if context.is_owner:
        return "owner"
    if context.platform in {"cli", "web"}:
        return "owner"
    return "user"
