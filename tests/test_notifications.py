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
    assert "回复“同意合并”立即合并" in napcat.messages[0][1]
    records = store.list_owner_notifications()
    assert len(records) == 2
    assert {record["status"] for record in records} == {"sent"}


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
