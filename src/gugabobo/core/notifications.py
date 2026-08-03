from __future__ import annotations

from typing import Protocol

from gugabobo.config import Settings, get_settings
from gugabobo.infra.napcat_client import NapCatClient
from gugabobo.infra.redaction import redact_sensitive
from gugabobo.memory.store import MemoryStore


class SyncTelegramNotificationClient(Protocol):
    def send_message(self, chat_id: str, text: str) -> None: ...


class OwnerNotifier:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings | None = None,
        napcat_client: NapCatClient | None = None,
        telegram_client: SyncTelegramNotificationClient | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self.napcat_client = napcat_client or NapCatClient()
        self.telegram_client = telegram_client

    def notify_pr_opened(
        self,
        number: int,
        url: str,
        title: str,
        github_owner: str = "",
        github_repo: str = "",
    ) -> list[int]:
        return self.ensure_pr_opened(number, url, title, github_owner, github_repo)

    def ensure_pr_opened(
        self,
        number: int,
        url: str,
        title: str,
        github_owner: str = "",
        github_repo: str = "",
    ) -> list[int]:
        owner, repo = self._repository(github_owner, github_repo)
        reference = f"{owner}/{repo} PR #{number}"
        content = (
            f"咕嘎BoBo 已提交 {reference}：{title}\n{url}\n\n"
            f"回复“同意合并”处理最近通知，或回复"
            f"“同意合并 {owner}/{repo}#{number}”/“拒绝合并 {owner}/{repo}#{number}”。"
        )
        return self.queue_and_deliver(
            self._pr_key(owner, repo, number, "opened"),
            "pr_opened",
            content,
        )

    def notify_pr_outcome(
        self,
        number: int,
        outcome: str,
        detail: str,
        skip_recipient: tuple[str, str] | None = None,
        github_owner: str = "",
        github_repo: str = "",
    ) -> list[int]:
        owner, repo = self._repository(github_owner, github_repo)
        label = "已合并" if outcome == "merged" else "已拒绝"
        content = f"咕嘎BoBo {owner}/{repo} PR #{number} {label}。\n{detail}".strip()
        return self.queue_and_deliver(
            self._pr_key(owner, repo, number, outcome),
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
        github_owner: str = "",
        github_repo: str = "",
    ) -> list[int]:
        owner, repo = self._repository(github_owner, github_repo)
        previous = previous_head_sha[:12] or "unknown"
        current = current_head_sha[:12] or "unknown"
        content = (
            f"咕嘎BoBo {owner}/{repo} PR #{number} 在授权后新增了提交。\n"
            f"原提交：{previous}\n当前提交：{current}\n{url}\n\n"
            f"请重新检查后回复“同意合并 {owner}/{repo}#{number}”。"
        )
        return self.queue_and_deliver(
            self._pr_key(
                owner,
                repo,
                number,
                f"head-changed:{previous_head_sha}:{current_head_sha}",
            ),
            "pr_head_changed",
            content,
        )

    def notify_deployment(
        self,
        status: str,
        revision: str,
        detail: str,
    ) -> list[int]:
        short_revision = revision[:12] or "unknown"
        if status == "deployed":
            content = f"咕嘎BoBo 已自动部署 {short_revision} 到服务器。\n{detail}".strip()
        else:
            content = (
                f"咕嘎BoBo 自动部署 {short_revision} 失败，生产服务已回滚。\n{detail}"
            ).strip()
        return self.queue_and_deliver(
            f"deployment:{revision}:{status}",
            f"deployment_{status}",
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
                if platform != "telegram" or self.telegram_client is not None:
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
                if self.telegram_client is None:
                    raise RuntimeError("async Telegram notification worker is not running")
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
        if self.telegram_client is None:
            records = [record for record in records if record["platform"] != "telegram"]
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

    def _repository(self, owner: str, repo: str) -> tuple[str, str]:
        return owner or self.settings.github_owner, repo or self.settings.github_repo

    def _pr_key(self, owner: str, repo: str, number: int, event: str) -> str:
        return f"pr:{owner.casefold()}/{repo.casefold()}:{number}:{event}"
