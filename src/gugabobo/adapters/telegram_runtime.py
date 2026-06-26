from __future__ import annotations

from typing import Any

from gugabobo.adapters.telegram import TelegramMessageEvent
from gugabobo.config import Settings
from gugabobo.core.access import evaluate_access
from gugabobo.core.agent import CoreAgent
from gugabobo.infra.logs import get_logger
from gugabobo.infra.telegram_client import TelegramClient


def handle_telegram_update(
    payload: dict[str, Any],
    agent: CoreAgent,
    settings: Settings,
    send_reply: bool = False,
    client: TelegramClient | None = None,
) -> dict[str, object]:
    logger = get_logger()
    event = TelegramMessageEvent.from_payload(payload)
    if not event.text:
        return {"status": "ignored", "reason": "empty message"}
    context = event.to_channel_context(
        owner_ids=settings.owner_telegram_id_set,
        group_wake_words=settings.telegram_group_wake_word_list,
        bot_username=settings.telegram_bot_username,
    )
    access = evaluate_access(context, agent.store)
    if not access.allowed:
        logger.info(
            "telegram message ignored source=%s user_id=%s reason=%s",
            context.source,
            context.user_id,
            access.reason,
        )
        return {"status": "ignored", "reason": access.reason}
    if not context.is_wake_triggered:
        route = agent.router.route(event.text)
        if route.skill == "feedback":
            feedback_id = agent.store.add_feedback(
                source=context.source,
                user_id=context.user_id,
                content=event.text,
            )
            logger.info("telegram feedback recorded id=%s source=%s", feedback_id, context.source)
            return {"status": "recorded", "feedback_id": feedback_id}
        return {"status": "ignored", "reason": "reply not allowed"}
    reply = agent.handle_context_message(event.text, context)
    if send_reply:
        telegram_client = client or TelegramClient()
        telegram_client.send_message(context.chat_id or context.user_id, reply)
        logger.info(
            "telegram message handled source=%s user_id=%s sent=true",
            context.source,
            context.user_id,
        )
        return {"status": "ok", "sent": True}
    logger.info("telegram message handled source=%s user_id=%s", context.source, context.user_id)
    return {"status": "ok", "sent": False, "reply_available": True}
