from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from types import TracebackType
from typing import Any

from aiogram import Dispatcher
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Update

from gugabobo.adapters.telegram import TelegramIncomingMessage
from gugabobo.config import Settings
from gugabobo.core.access import context_with_access_role, evaluate_access, role_can_use_skill
from gugabobo.core.agent import CoreAgent
from gugabobo.core.lifecycle import is_merge_command
from gugabobo.infra.logs import get_logger
from gugabobo.infra.telegram_client import TelegramClient
from gugabobo.memory.store import MemoryStore

TelegramPollingResult = Callable[[int, dict[str, object]], None]


class TelegramNotificationWorker:
    def __init__(
        self,
        store: MemoryStore,
        client: TelegramClient | None = None,
    ) -> None:
        self.store = store
        self.client = client or TelegramClient()
        self.owns_client = client is None

    async def run(self, interval: float = 5.0) -> None:
        try:
            while True:
                await self.deliver_pending()
                await asyncio.sleep(interval)
        finally:
            if self.owns_client:
                await self.client.close()

    async def deliver_pending(self, limit: int = 50) -> dict[str, int]:
        records = await asyncio.to_thread(
            self.store.list_owner_notifications,
            limit,
            True,
        )
        telegram_records = [record for record in records if record["platform"] == "telegram"]
        sent = 0
        for record in telegram_records:
            notification_id = int(record["id"])
            notification = await asyncio.to_thread(
                self.store.claim_owner_notification,
                notification_id,
            )
            if not notification:
                continue
            try:
                await self.client.send_message(
                    str(notification["recipient_id"]),
                    str(notification["content"]),
                )
            except Exception as error:
                await asyncio.to_thread(
                    self.store.finish_owner_notification,
                    notification_id,
                    "failed",
                    str(error)[:1000],
                )
                continue
            await asyncio.to_thread(
                self.store.finish_owner_notification,
                notification_id,
                "sent",
            )
            sent += 1
        return {"attempted": len(telegram_records), "sent": sent}


class TelegramService:
    def __init__(
        self,
        agent: CoreAgent,
        settings: Settings,
        send_replies: bool,
        client: TelegramClient | None = None,
        on_result: TelegramPollingResult | None = None,
    ) -> None:
        self.agent = agent
        self.settings = settings
        self.send_replies = send_replies
        self.client = client or TelegramClient()
        self.on_result = on_result
        self.retry_failed_updates = False
        self.dispatcher = Dispatcher(disable_fsm=True)
        self.dispatcher.update.register(self._dispatch_update)

    async def __aenter__(self) -> TelegramService:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def process_raw_update(self, payload: dict[str, Any]) -> dict[str, object]:
        if not self.client.configured:
            return await self.process_update(Update.model_validate(payload))
        result = await self.dispatcher.feed_raw_update(self.client.bot, payload)
        return result if isinstance(result, dict) else {"status": "ignored"}

    async def process_update(self, update: Update) -> dict[str, object]:
        return await self._dispatch_update(update)

    async def start_polling(self, timeout: int) -> None:
        self.retry_failed_updates = True
        await self.client.set_commands()
        await self.dispatcher.start_polling(
            self.client.bot,
            polling_timeout=timeout,
            handle_as_tasks=False,
            allowed_updates=["message", "edited_message"],
            close_bot_session=False,
        )

    async def close(self) -> None:
        await self.client.close()

    async def _dispatch_update(self, update: Update) -> dict[str, object]:
        backoff = 1
        while True:
            try:
                result = await self._process_update(update)
                if self.on_result:
                    self.on_result(update.update_id, result)
                return result
            except Exception as error:
                if not self.retry_failed_updates:
                    raise
                get_logger().warning("telegram update %d failed: %s", update.update_id, error)
                await asyncio.sleep(min(backoff, 60))
                backoff = min(backoff * 2, 60)

    async def _process_update(self, update: Update) -> dict[str, object]:
        incoming = TelegramIncomingMessage.from_update(update)
        if incoming is None or not incoming.has_content():
            return await self._finish(incoming, {"status": "ignored", "reason": "empty message"})

        existing = await asyncio.to_thread(
            self.agent.store.get_inbound_event,
            "telegram",
            incoming.update_id,
        )
        if existing and existing["status"] == "completed":
            result = dict(existing.get("result", {}))
            result["duplicate"] = True
            return result
        existing = await asyncio.to_thread(
            self.agent.store.begin_inbound_event,
            "telegram",
            incoming.update_id,
        )

        context = incoming.to_channel_context(
            owner_ids=self.settings.owner_telegram_id_set,
            group_wake_words=self.settings.telegram_group_wake_word_list,
            bot_username=self.settings.telegram_bot_username,
        )
        access = await asyncio.to_thread(evaluate_access, context, self.agent.store)
        if not access.allowed:
            get_logger().info(
                "telegram message ignored source=%s user_id=%s reason=%s",
                context.source,
                context.user_id,
                access.reason,
            )
            return await self._finish(
                incoming,
                {"status": "ignored", "reason": access.reason},
            )

        context = context_with_access_role(context, access)
        if self._is_community_command(incoming.text):
            return await self._send_community_menu(incoming, context.chat_id or context.user_id)
        if self._is_summary_command(incoming.text):
            return await self._send_summary_bot(incoming, context.chat_id or context.user_id)
        if self._is_developers_command(incoming.text):
            return await self._send_developers(incoming, context.chat_id or context.user_id)
        if self._is_github_command(incoming.text):
            return await self._send_github_links(incoming, context.chat_id or context.user_id)
        owner_lifecycle_command = context.is_owner and is_merge_command(incoming.text)
        if not context.is_wake_triggered and not owner_lifecycle_command:
            route = self.agent.router.route(incoming.text)
            if route.skill == "feedback":
                if not role_can_use_skill(access.role, "feedback"):
                    return await self._finish(
                        incoming,
                        {"status": "ignored", "reason": "insufficient role"},
                    )
                feedback_id = await asyncio.to_thread(
                    self.agent.store.add_feedback,
                    source=context.source,
                    user_id=context.user_id,
                    content=incoming.text,
                )
                return await self._finish(
                    incoming,
                    {"status": "recorded", "feedback_id": feedback_id},
                )
            return await self._finish(
                incoming,
                {"status": "ignored", "reason": "reply not allowed"},
            )

        cached_reply = str(existing.get("reply", "")) if existing else ""
        if existing and existing["status"] == "reply_ready" and cached_reply:
            reply = cached_reply
        else:
            images = None
            if incoming.photo_file_ids and self.client.configured:
                images = await self.client.file_ids_to_data_uris(
                    list(incoming.photo_file_ids)
                ) or None
            reply = await asyncio.to_thread(
                self.agent.handle_context_message,
                incoming.text,
                context,
                images,
            )
            await asyncio.to_thread(
                self.agent.store.save_inbound_event_reply,
                "telegram",
                incoming.update_id,
                reply,
                {"status": "reply_ready", "sent": False},
            )

        if self.send_replies:
            try:
                await self.client.send_message(context.chat_id or context.user_id, reply)
            except Exception as error:
                await asyncio.to_thread(
                    self.agent.store.fail_inbound_event,
                    "telegram",
                    incoming.update_id,
                    str(error),
                )
                raise
            result = {"status": "ok", "sent": True}
        else:
            result = {"status": "ok", "sent": False, "reply_available": True}
        return await self._finish(incoming, result)

    async def _send_community_menu(
        self,
        incoming: TelegramIncomingMessage,
        chat_id: str,
    ) -> dict[str, object]:
        links = {
            "group": self.settings.telegram_community_group_url,
            "bot": self.settings.telegram_companion_bot_url,
            "channel": self.settings.telegram_announcement_channel_url,
            "summary_bot": self.settings.telegram_summary_bot_url,
            "developer_gugabobo": self.settings.telegram_developer_gugabobo_url,
            "developer_scarletkc": self.settings.telegram_developer_scarletkc_url,
            "github_scarletkc": self.settings.telegram_github_scarletkc_url,
            "github_fogmoe": self.settings.telegram_github_fogmoe_url,
            "github_geyugong": self.settings.telegram_github_geyugong_url,
            "github_gugabobo": self.settings.telegram_github_gugabobo_url,
        }
        text = (
            "Telegram 社区入口：\n"
            "• 詩音閣群组\n"
            "• 雾萌机器人\n"
            "• FOGMOE 频道\n"
            "• @rigerubot 群组总结\n"
            "• 开发者 @woshigugabobo、@scarletkc\n"
            "• GitHub：ScarletKC、FogMoe、GeYugong、GugaBoBo-s"
        )
        if self.send_replies:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="加入詩音閣", url=links["group"])],
                    [InlineKeyboardButton(text="打开雾萌机器人", url=links["bot"])],
                    [InlineKeyboardButton(text="关注 FOGMOE", url=links["channel"])],
                    [InlineKeyboardButton(text="使用群组总结", url=links["summary_bot"])],
                    [
                        InlineKeyboardButton(
                            text="开发者 @woshigugabobo",
                            url=links["developer_gugabobo"],
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="开发者 @scarletkc",
                            url=links["developer_scarletkc"],
                        )
                    ],
                    [InlineKeyboardButton(text="GitHub · ScarletKC", url=links["github_scarletkc"])],
                    [InlineKeyboardButton(text="GitHub · FogMoe", url=links["github_fogmoe"])],
                    [InlineKeyboardButton(text="GitHub · GeYugong", url=links["github_geyugong"])],
                    [InlineKeyboardButton(text="GitHub · GugaBoBo-s", url=links["github_gugabobo"])],
                ]
            )
            await self.client.send_message(chat_id, text, reply_markup=keyboard)
        return await self._finish(
            incoming,
            {
                "status": "ok",
                "sent": self.send_replies,
                "reply_available": not self.send_replies,
                "community_links": links,
            },
        )

    async def _send_github_links(
        self,
        incoming: TelegramIncomingMessage,
        chat_id: str,
    ) -> dict[str, object]:
        links = {
            "ScarletKC": self.settings.telegram_github_scarletkc_url,
            "FogMoe": self.settings.telegram_github_fogmoe_url,
            "GeYugong": self.settings.telegram_github_geyugong_url,
            "GugaBoBo-s": self.settings.telegram_github_gugabobo_url,
        }
        text = "关联 GitHub：\n• ScarletKC\n• FogMoe\n• GeYugong\n• GugaBoBo-s"
        if self.send_replies:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=name, url=url)] for name, url in links.items()
                ]
            )
            await self.client.send_message(chat_id, text, reply_markup=keyboard)
        return await self._finish(
            incoming,
            {
                "status": "ok",
                "sent": self.send_replies,
                "reply_available": not self.send_replies,
                "github_links": links,
            },
        )

    async def _send_developers(
        self,
        incoming: TelegramIncomingMessage,
        chat_id: str,
    ) -> dict[str, object]:
        developers = {
            "@woshigugabobo": self.settings.telegram_developer_gugabobo_url,
            "@scarletkc": self.settings.telegram_developer_scarletkc_url,
        }
        text = "项目开发者：\n• @woshigugabobo\n• @scarletkc"
        if self.send_replies:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=username, url=url)]
                    for username, url in developers.items()
                ]
            )
            await self.client.send_message(chat_id, text, reply_markup=keyboard)
        return await self._finish(
            incoming,
            {
                "status": "ok",
                "sent": self.send_replies,
                "reply_available": not self.send_replies,
                "developers": developers,
            },
        )

    async def _send_summary_bot(
        self,
        incoming: TelegramIncomingMessage,
        chat_id: str,
    ) -> dict[str, object]:
        text = "群组总结由 @rigerubot 提供。请由群管理员将它添加到目标群组后使用。"
        if self.send_replies:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="添加 @rigerubot 到群组",
                            url=self.settings.telegram_summary_bot_url,
                        )
                    ]
                ]
            )
            await self.client.send_message(chat_id, text, reply_markup=keyboard)
        return await self._finish(
            incoming,
            {
                "status": "ok",
                "sent": self.send_replies,
                "reply_available": not self.send_replies,
                "summary_bot": "@rigerubot",
                "summary_bot_url": self.settings.telegram_summary_bot_url,
            },
        )

    @staticmethod
    def _is_community_command(text: str) -> bool:
        command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold()
        return command in {"/community", "/fogmoe"}

    @staticmethod
    def _is_summary_command(text: str) -> bool:
        command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold()
        return command == "/summary"

    @staticmethod
    def _is_developers_command(text: str) -> bool:
        command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold()
        return command == "/developers"

    @staticmethod
    def _is_github_command(text: str) -> bool:
        command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold()
        return command == "/github"

    async def _finish(
        self,
        incoming: TelegramIncomingMessage | None,
        result: dict[str, object],
    ) -> dict[str, object]:
        if incoming is not None:
            await asyncio.to_thread(
                self.agent.store.complete_inbound_event,
                "telegram",
                incoming.update_id,
                result,
            )
        return result


async def run_telegram_polling(
    agent: CoreAgent,
    settings: Settings,
    send_reply: bool,
    timeout: int,
    on_result: TelegramPollingResult | None = None,
) -> None:
    async with TelegramService(
        agent=agent,
        settings=settings,
        send_replies=send_reply,
        on_result=on_result,
    ) as service:
        notification_worker = TelegramNotificationWorker(agent.store, service.client)
        notification_task = asyncio.create_task(notification_worker.run())
        try:
            await service.start_polling(timeout)
        finally:
            notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await notification_task
