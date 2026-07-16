from __future__ import annotations

from typing import Any

from gugabobo.adapters.telegram import TelegramMessageEvent
from gugabobo.config import Settings
from gugabobo.core.access import context_with_access_role, evaluate_access, role_can_use_skill
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
    event_id = event.update_id
    existing = agent.store.get_inbound_event("telegram", event_id) if event_id else None
    if existing and existing["status"] == "completed":
        result = dict(existing.get("result", {}))
        result["duplicate"] = True
        return result
    if event_id:
        existing = agent.store.begin_inbound_event("telegram", event_id)
    if not event.has_content():
        result = {"status": "ignored", "reason": "empty message"}
        if event_id:
            agent.store.complete_inbound_event("telegram", event_id, result)
        return result
    telegram_client = client or TelegramClient()
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
        result = {"status": "ignored", "reason": access.reason}
        if event_id:
            agent.store.complete_inbound_event("telegram", event_id, result)
        return result
    context = context_with_access_role(context, access)
    if not context.is_wake_triggered:
        route = agent.router.route(event.text)
        if route.skill == "feedback":
            if not role_can_use_skill(access.role, "feedback"):
                result = {"status": "ignored", "reason": "insufficient role"}
                if event_id:
                    agent.store.complete_inbound_event("telegram", event_id, result)
                return result
            feedback_id = agent.store.add_feedback(
                source=context.source,
                user_id=context.user_id,
                content=event.text,
            )
            logger.info("telegram feedback recorded id=%s source=%s", feedback_id, context.source)
            result = {"status": "recorded", "feedback_id": feedback_id}
            if event_id:
                agent.store.complete_inbound_event("telegram", event_id, result)
            return result
        result = {"status": "ignored", "reason": "reply not allowed"}
        if event_id:
            agent.store.complete_inbound_event("telegram", event_id, result)
        return result
    cached_reply = str(existing.get("reply", "")) if existing else ""
    if existing and existing["status"] == "reply_ready" and cached_reply:
        reply = cached_reply
    else:
        images = None
        if event.photo_file_ids and telegram_client.configured:
            images = telegram_client.file_ids_to_data_uris(list(event.photo_file_ids)) or None
        reply = agent.handle_context_message(event.text, context, images=images)
        if event_id:
            agent.store.save_inbound_event_reply(
                "telegram",
                event_id,
                reply,
                {"status": "reply_ready", "sent": False},
            )
    if send_reply:
        try:
            telegram_client.send_message(context.chat_id or context.user_id, reply)
        except Exception as error:
            if event_id:
                agent.store.fail_inbound_event("telegram", event_id, str(error))
            raise
        logger.info(
            "telegram message handled source=%s user_id=%s sent=true",
            context.source,
            context.user_id,
        )
        result = {"status": "ok", "sent": True}
        if event_id:
            agent.store.complete_inbound_event("telegram", event_id, result)
        return result
    logger.info("telegram message handled source=%s user_id=%s", context.source, context.user_id)
    result = {"status": "ok", "sent": False, "reply_available": True}
    if event_id:
        agent.store.complete_inbound_event("telegram", event_id, result)
    return result
