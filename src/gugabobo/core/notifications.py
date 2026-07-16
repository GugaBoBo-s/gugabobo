from __future__ import annotations

from gugabobo.config import Settings, get_settings
from gugabobo.infra.napcat_client import NapCatClient
from gugabobo.infra.redaction import redact_sensitive
from gugabobo.infra.telegram_client import TelegramClient
from gugabobo.memory.store import MemoryStore


class OwnerNotifier:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings | None = None,
        napcat_client: NapCatClient | None = None,
        telegram_client: TelegramClient | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self.napcat_client = napcat_client or NapCatClient()
        self.telegram_client = telegram_client or TelegramClient()

    def notify_pr_opened(self, number: int, url: str, title: str) -> list[int]:
        content = (
            f"咕嘎BoBo 已提交 PR #{number}：{title}\n{url}\n\n"
            "回复“同意合并”立即合并，或回复“拒绝合并”关闭。"
        )
        return self.queue_and_deliver(f"pr:{number}:opened", "pr_opened", content)

    def notify_pr_outcome(
        self,
        number: int,
        outcome: str,
        detail: str,
        skip_recipient: tuple[str, str] | None = None,
    ) -> list[int]:
        label = "已合并" if outcome == "merged" else "已拒绝"
        content = f"咕嘎BoBo PR #{number} {label}。\n{detail}".strip()
        return self.queue_and_deliver(
            f"pr:{number}:{outcome}",
            f"pr_{outcome}",
            content,
            skip_recipient=skip_recipient,
        )

    def notify_pr_head_changed(
        self,
        number: int,
        url: str,
        previous_head_sha: str,
        current_head_sha: str,
    ) -> list[int]:
        previous = previous_head_sha[:12] or "unknown"
        current = current_head_sha[:12] or "unknown"
        content = (
            f"咕嘎BoBo PR #{number} 在授权后新增了提交。\n"
            f"原提交：{previous}\n当前提交：{current}\n{url}\n\n"
            f"请重新检查后回复“同意合并 PR #{number}”。"
        )
        return self.queue_and_deliver(
            f"pr:{number}:head-changed:{previous_head_sha}:{current_head_sha}",
            "pr_head_changed",
            content,
        )

    def queue_and_deliver(
        self,
        dedupe_key: str,
        event_type: str,
        content: str,
        skip_recipient: tuple[str, str] | None = None,
    ) -> list[int]:
        ids: list[int] = []
        for platform, recipient_ids in (
            ("qq", self.settings.owner_qq_id_set),
            ("telegram", self.settings.owner_telegram_id_set),
        ):
            for recipient_id in sorted(recipient_ids):
                if skip_recipient == (platform, recipient_id):
                    continue
                notification_id = self.store.queue_owner_notification(
                    dedupe_key=dedupe_key,
                    event_type=event_type,
                    platform=platform,
                    recipient_id=recipient_id,
                    content=content,
                )
                ids.append(notification_id)
                self.deliver(notification_id)
        return ids

    def deliver(self, notification_id: int) -> bool:
        notification = self.store.claim_owner_notification(notification_id)
        if not notification:
            return False
        try:
            platform = str(notification["platform"])
            recipient_id = str(notification["recipient_id"])
            content = str(notification["content"])
            if platform == "qq":
                self.napcat_client.send_private_msg(recipient_id, content)
            elif platform == "telegram":
                self.telegram_client.send_message(recipient_id, content)
            else:
                raise RuntimeError(f"unsupported notification platform: {platform}")
        except Exception as error:
            self.store.finish_owner_notification(
                notification_id,
                "failed",
                self._safe_error(error),
            )
            return False
        self.store.finish_owner_notification(notification_id, "sent")
        return True

    def retry_pending(self, limit: int = 50) -> dict[str, int]:
        records = self.store.list_owner_notifications(limit=limit, retryable_only=True)
        sent = sum(1 for record in records if self.deliver(int(record["id"])))
        return {"attempted": len(records), "sent": sent}

    def _safe_error(self, error: object) -> str:
        return redact_sensitive(
            error,
            (
                self.settings.napcat_access_token,
                self.settings.telegram_bot_token,
                self.settings.github_token,
            ),
        )[:1000]
