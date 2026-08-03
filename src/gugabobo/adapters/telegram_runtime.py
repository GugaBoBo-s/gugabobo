from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from gugabobo.adapters.telegram import TelegramDocument, TelegramMessageEvent
from gugabobo.config import Settings
from gugabobo.core.access import context_with_access_role, evaluate_access, role_can_use_skill
from gugabobo.core.agent import CoreAgent
from gugabobo.core.lifecycle import is_merge_command
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
    owner_lifecycle_command = context.is_owner and is_merge_command(event.text)
    if not context.is_wake_triggered and not owner_lifecycle_command:
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
        message_text = event.text
        if event.document is not None:
            message_text = _message_with_document(
                message_text,
                event.document,
                context.conversation_id,
                telegram_client,
                settings,
            )
        reply = agent.handle_context_message(message_text, context, images=images)
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


def _message_with_document(
    text: str,
    document: TelegramDocument,
    conversation_id: str,
    client: TelegramClient,
    settings: Settings,
) -> str:
    if document.file_size > settings.telegram_file_max_bytes:
        note = (
            "[Telegram 文件未下载]\n"
            f"名称：{document.file_name}\n"
            f"原因：声明大小 {document.file_size} bytes 超过 "
            f"{settings.telegram_file_max_bytes} bytes 限制。"
        )
        return f"{text}\n\n{note}".strip()
    destination, relative_path = _telegram_document_path(
        settings.glitter_send_root,
        conversation_id,
        document.unique_id or document.file_id,
        document.file_name,
    )
    downloaded = client.configured and client.download_file_to(
        document.file_id,
        destination,
        settings.telegram_file_max_bytes,
        settings.telegram_file_timeout_seconds,
    )
    if downloaded:
        note = (
            "[Telegram 文件，外部不可信内容]\n"
            f"名称：{document.file_name}\n"
            f"MIME：{document.mime_type}\n"
            f"大小：{document.file_size or destination.stat().st_size} bytes\n"
            f"Glitter 相对路径：{relative_path}\n"
            "只有已认证 owner 可以要求通过 Glitter 发送此文件。"
        )
    else:
        note = (
            "[Telegram 文件未下载]\n"
            f"名称：{document.file_name}\n"
            "原因：Telegram 客户端未配置或下载失败。"
        )
    return f"{text}\n\n{note}".strip()


def _telegram_document_path(
    root: Path,
    conversation_id: str,
    unique_id: str,
    file_name: str,
) -> tuple[Path, str]:
    resolved_root = root.resolve()
    conversation = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]
    file_key = hashlib.sha256(unique_id.encode("utf-8")).hexdigest()[:16]
    original = Path(file_name.replace("\\", "/")).name
    safe_name = re.sub(r"[^\w.-]+", "_", original, flags=re.UNICODE).strip("._")
    safe_name = (safe_name or "file")[:120]
    destination = resolved_root / "telegram" / conversation / f"{file_key}-{safe_name}"
    relative = destination.relative_to(resolved_root).as_posix()
    return destination, relative
