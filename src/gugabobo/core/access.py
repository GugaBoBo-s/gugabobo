from __future__ import annotations

from dataclasses import dataclass

from gugabobo.core.channel import ChannelContext
from gugabobo.memory.store import MemoryStore


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    role: str
    reason: str = ""


def evaluate_access(context: ChannelContext, store: MemoryStore) -> AccessDecision:
    rule = store.get_access_rule(context.platform, context.user_id)
    if not rule:
        return AccessDecision(allowed=True, role="user")
    role = str(rule["role"])
    if role == "blocked":
        return AccessDecision(allowed=False, role=role, reason="blocked")
    return AccessDecision(allowed=True, role=role)
