import asyncio

from gugabobo.adapters.telegram_runtime import TelegramNotificationWorker
from gugabobo.config import Settings
from gugabobo.core.notifications import OwnerNotifier
from gugabobo.memory.store import MemoryStore


class FakeNapCat:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.fail = False

    def send_private_msg(self, user_id: str, message: str) -> None:
        if self.fail:
            raise RuntimeError("napcat unavailable")
        self.messages.append((user_id, message))


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_message(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


class AsyncFakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


def test_owner_notification_sends_both_channels_and_deduplicates(tmp_path) -> None:
    store = MemoryStore(tmp_path / "notifications.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "notifications.db",
        owner_qq_ids="10001",
        owner_telegram_ids="20001",
    )
    napcat = FakeNapCat()
    telegram = FakeTelegram()
    notifier = OwnerNotifier(store, settings, napcat, telegram)

    notifier.notify_pr_opened(15, "https://example/pull/15", "Update docs")
    notifier.notify_pr_opened(15, "https://example/pull/15", "Update docs")

    assert len(napcat.messages) == 1
    assert len(telegram.messages) == 1
    assert "GugaBoBo-s/gugabobo PR #15" in napcat.messages[0][1]
    records = store.list_owner_notifications()
    assert len(records) == 2
    assert {record["status"] for record in records} == {"sent"}


def test_async_worker_delivers_queued_telegram_notification(tmp_path) -> None:
    store = MemoryStore(tmp_path / "async-notifications.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "async-notifications.db",
        owner_telegram_ids="20001",
    )
    notifier = OwnerNotifier(store, settings, FakeNapCat())
    telegram = AsyncFakeTelegram()

    notifier.notify_pr_opened(15, "https://example/pull/15", "Update docs")
    result = asyncio.run(TelegramNotificationWorker(store, telegram).deliver_pending())

    assert result == {"attempted": 1, "sent": 1}
    assert telegram.messages[0][0] == "20001"
    assert "GugaBoBo-s/gugabobo PR #15" in telegram.messages[0][1]
    assert "https://example/pull/15" in telegram.messages[0][1]
    assert store.list_owner_notifications()[0]["status"] == "sent"


def test_same_pull_request_number_in_different_repositories_does_not_collide(tmp_path) -> None:
    store = MemoryStore(tmp_path / "repository-keys.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "repository-keys.db",
        owner_qq_ids="10001",
        owner_telegram_ids="",
    )
    napcat = FakeNapCat()
    notifier = OwnerNotifier(store, settings, napcat, FakeTelegram())

    notifier.notify_pr_opened(
        1,
        "https://example/gugabobo/1",
        "First",
        "GugaBoBo-s",
        "gugabobo",
    )
    notifier.notify_pr_opened(
        1,
        "https://example/test07/1",
        "Second",
        "GugaBoBo-s",
        "test07",
    )

    records = store.list_owner_notifications()
    assert len(napcat.messages) == 2
    assert len(records) == 2
    assert len({record["dedupe_key"] for record in records}) == 2


def test_outcome_notification_skips_reply_channel(tmp_path) -> None:
    store = MemoryStore(tmp_path / "skip.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "skip.db",
        owner_qq_ids="10001",
        owner_telegram_ids="20001",
    )
    napcat = FakeNapCat()
    telegram = FakeTelegram()
    notifier = OwnerNotifier(store, settings, napcat, telegram)

    notifier.notify_pr_outcome(
        15,
        "merged",
        "done",
        skip_recipient=("telegram", "20001"),
    )

    assert len(napcat.messages) == 1
    assert telegram.messages == []


def test_failed_notification_is_retried(tmp_path) -> None:
    store = MemoryStore(tmp_path / "retry.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "retry.db",
        owner_qq_ids="10001",
        owner_telegram_ids="",
    )
    napcat = FakeNapCat()
    napcat.fail = True
    notifier = OwnerNotifier(store, settings, napcat, FakeTelegram())

    notifier.notify_pr_outcome(15, "merged", "done")

    record = store.list_owner_notifications()[0]
    assert record["status"] == "failed"
    assert record["attempts"] == 1

    napcat.fail = False
    result = notifier.retry_pending()

    assert result == {"attempted": 1, "sent": 1}
    record = store.list_owner_notifications()[0]
    assert record["status"] == "sent"
    assert record["attempts"] == 2


def test_stale_sending_notification_is_recovered_after_lease(tmp_path) -> None:
    store = MemoryStore(tmp_path / "stale.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "stale.db",
        owner_qq_ids="10001",
        owner_telegram_ids="",
    )
    napcat = FakeNapCat()
    notifier = OwnerNotifier(store, settings, napcat, FakeTelegram())
    notification_id = store.queue_owner_notification(
        "pr:15:merged:qq:10001",
        "pr_merged",
        "qq",
        "10001",
        "done",
    )

    claimed = store.claim_owner_notification(notification_id)
    fresh_result = notifier.retry_pending()

    assert claimed is not None
    assert fresh_result == {"attempted": 0, "sent": 0}
    assert napcat.messages == []

    with store.connect() as conn:
        conn.execute(
            "UPDATE owner_notifications SET updated_at = datetime('now', '-6 minutes') "
            "WHERE id = ?",
            (notification_id,),
        )

    stale_result = notifier.retry_pending()
    record = store.list_owner_notifications()[0]

    assert stale_result == {"attempted": 1, "sent": 1}
    assert napcat.messages == [("10001", "done")]
    assert record["status"] == "sent"
    assert record["attempts"] == 2


def test_deployment_notification_sends_result_once_per_revision(tmp_path) -> None:
    store = MemoryStore(tmp_path / "deployment-notification.db")
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "deployment-notification.db",
        owner_qq_ids="10001",
        owner_telegram_ids="20001",
    )
    napcat = FakeNapCat()
    telegram = FakeTelegram()
    notifier = OwnerNotifier(store, settings, napcat, telegram)

    notifier.notify_deployment("deployed", "abcdef1234567890", "health check passed")
    notifier.notify_deployment("deployed", "abcdef1234567890", "health check passed")

    assert len(napcat.messages) == 1
    assert len(telegram.messages) == 1
    assert "已自动部署 abcdef123456" in napcat.messages[0][1]
