import sqlite3

from gugabobo.config import Settings
from gugabobo.core.channel import ChannelContext
from gugabobo.core.lifecycle import PullRequestLifecycleService, parse_merge_command
from gugabobo.infra.github_client import MergeResult
from gugabobo.memory.store import MemoryStore


class FakeGitHub:
    configured = True
    owner = "GugaBoBo-s"
    repo = "gugabobo"

    def __init__(self, checks_status: str = "success") -> None:
        self.checks_status = checks_status
        self.merge_fails = False
        self.remote = {
            "state": "open",
            "merged": False,
            "merged_at": None,
            "merge_commit_sha": "",
            "head": {"sha": "head-sha"},
        }
        self.merged_numbers: list[int] = []
        self.merged_shas: list[str] = []
        self.closed_numbers: list[int] = []

    def get_pull_request(self, number: int) -> dict[str, object]:
        return self.remote

    def get_checks_status(self, ref: str) -> str:
        return self.checks_status

    def merge_pull_request(
        self,
        number: int,
        commit_title: str,
        merge_method: str = "squash",
        sha: str = "",
    ) -> MergeResult:
        if self.merge_fails:
            raise RuntimeError("GitHub temporarily rejected merge")
        self.merged_numbers.append(number)
        self.merged_shas.append(sha)
        return MergeResult(merged=True, sha="merge-sha", message="merged")

    def close_pull_request(self, number: int) -> dict[str, object]:
        self.closed_numbers.append(number)
        self.remote["state"] = "closed"
        return self.remote


class FakeNotifier:
    def __init__(self) -> None:
        self.outcomes: list[tuple[int, str, str, tuple[str, str] | None]] = []
        self.head_changes: list[tuple[int, str, str, str]] = []

    def notify_pr_outcome(
        self,
        number: int,
        outcome: str,
        detail: str,
        skip_recipient: tuple[str, str] | None = None,
    ) -> list[int]:
        self.outcomes.append((number, outcome, detail, skip_recipient))
        return []

    def retry_pending(self, limit: int = 50) -> dict[str, int]:
        return {"attempted": 0, "sent": 0}

    def notify_pr_head_changed(
        self,
        number: int,
        url: str,
        previous_head_sha: str,
        current_head_sha: str,
    ) -> list[int]:
        self.head_changes.append((number, url, previous_head_sha, current_head_sha))
        return []

def build_service(tmp_path, checks_status: str = "success"):
    store = MemoryStore(tmp_path / "lifecycle.db")
    task_id = store.add_task(title="Improve lifecycle")
    improvement_id = store.add_improvement_task(task_id=task_id, repo="GugaBoBo-s/gugabobo")
    pr_id = store.add_pull_request(
        improvement_task_id=improvement_id,
        github_owner="GugaBoBo-s",
        github_repo="gugabobo",
        number=15,
        url="https://github.com/GugaBoBo-s/gugabobo/pull/15",
        branch_name="gugabobo/improvement-15",
    )
    settings = Settings(
        env="test",
        data_dir=tmp_path,
        db_path=tmp_path / "lifecycle.db",
        github_token="token",
        github_owner="GugaBoBo-s",
        github_repo="gugabobo",
        owner_qq_ids="",
        owner_telegram_ids="",
    )
    github = FakeGitHub(checks_status)
    notifier = FakeNotifier()
    service = PullRequestLifecycleService(store, settings, github, notifier)
    return store, pr_id, github, notifier, service


def test_parse_merge_commands() -> None:
    assert parse_merge_command("同意合并 PR #15") == ("approve", 15)
    assert parse_merge_command("/merge 15") == ("approve", 15)
    assert parse_merge_command("拒绝合并 PR #15") == ("reject", 15)
    assert parse_merge_command("/reject-merge 15") == ("reject", 15)
    assert parse_merge_command("同意合并") == ("approve", None)
    assert parse_merge_command("拒绝合并") == ("reject", None)
    assert parse_merge_command("聊聊 PR 15") is None


def test_merge_authorization_schema_is_migrated(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE merge_authorizations ("
            "pull_request_id INTEGER PRIMARY KEY, decision TEXT NOT NULL, "
            "status TEXT NOT NULL, actor_platform TEXT NOT NULL, actor_source TEXT NOT NULL, "
            "actor_user_id TEXT NOT NULL, command TEXT NOT NULL DEFAULT '', "
            "detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )

    store = MemoryStore(db_path)

    with store.connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(merge_authorizations)")
        }
    assert "authorized_head_sha" in columns


def test_non_owner_cannot_authorize_merge(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)
    context = ChannelContext(
        platform="telegram",
        channel_type="private",
        source="telegram_private",
        user_id="other",
        conversation_id="telegram:other",
    )

    reply = service.handle_command("同意合并 PR #15", context)

    assert reply == "只有已登记的主人可以批准或拒绝合并 PR。"
    assert store.get_merge_authorization(pr_id) is None
    assert github.merged_numbers == []
    assert notifier.outcomes == []


def test_successful_checks_merge_immediately(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)

    outcome = service.approve_merge(15, ChannelContext.local(), "/merge 15")

    assert outcome.status == "merged"
    assert github.merged_numbers == [15]
    assert github.merged_shas == ["head-sha"]
    assert store.get_pull_request(pr_id)["status"] == "merged"
    assert store.get_merge_authorization(pr_id)["status"] == "merged"
    assert store.list_improvement_reflections()[0]["outcome"] == "merged"
    assert store.list_deployment_records()[0]["target_revision"] == "merge-sha"
    assert notifier.outcomes[0][1] == "merged"


def test_owner_approval_merges_regardless_of_check_visibility(tmp_path) -> None:
    for checks_status in ("pending", "unknown", "failure"):
        store, pr_id, github, notifier, service = build_service(
            tmp_path / checks_status,
            checks_status,
        )

        outcome = service.approve_merge(15, ChannelContext.local(), "/merge 15")

        assert outcome.status == "merged"
        assert github.merged_numbers == [15]
        assert store.get_merge_authorization(pr_id)["status"] == "merged"


def test_implicit_approval_uses_latest_pr_notification(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)
    notification_id = store.queue_owner_notification(
        "pr:15:opened",
        "pr_opened",
        "telegram",
        "owner-1",
        "opened",
    )
    store.claim_owner_notification(notification_id)
    store.finish_owner_notification(notification_id, "sent")
    context = ChannelContext(
        platform="telegram",
        channel_type="private",
        source="telegram_private",
        user_id="owner-1",
        conversation_id="telegram:user:owner-1",
        is_owner=True,
        is_wake_triggered=True,
    )

    reply = service.handle_command("同意合并", context)

    assert reply == "PR #15 已合并。"
    assert github.merged_numbers == [15]
    assert store.get_pull_request(pr_id)["status"] == "merged"
    assert notifier.outcomes[0][3] == ("telegram", "owner-1")


def test_github_rejection_is_retried_by_daemon(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)
    github.merge_fails = True

    outcome = service.approve_merge(15, ChannelContext.local(), "/merge 15")

    assert outcome.status == "merge_pending"
    assert store.get_merge_authorization(pr_id)["status"] == "merge_pending"
    assert store.list_improvement_reflections()[0]["outcome"] == "merge_failed"

    github.merge_fails = False
    tick = service.tick()

    assert tick["merged"] == 1
    assert github.merged_numbers == [15]


def test_new_head_requires_fresh_owner_authorization(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)
    github.merge_fails = True

    first = service.approve_merge(15, ChannelContext.local(), "/merge 15")
    github.remote["head"] = {"sha": "new-head-sha"}
    github.merge_fails = False
    tick = service.tick()

    assert first.status == "merge_pending"
    assert tick["merged"] == 0
    assert github.merged_numbers == []
    assert store.get_merge_authorization(pr_id)["status"] == "head_changed"
    assert notifier.head_changes[0][2:] == ("head-sha", "new-head-sha")

    second = service.approve_merge(15, ChannelContext.local(), "同意合并 PR #15")

    assert second.status == "merged"
    assert github.merged_shas == ["new-head-sha"]


def test_fresh_merge_lease_prevents_duplicate_merge_call(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)
    store.upsert_merge_authorization(
        pull_request_id=pr_id,
        decision="approved",
        status="approved",
        authorized_head_sha="head-sha",
        actor_platform="cli",
        actor_source="cli",
        actor_user_id="local",
    )
    assert store.claim_merge_authorization(pr_id, "head-sha") is not None

    pending = service.process(pr_id)

    assert pending.status == "merge_pending"
    assert github.merged_numbers == []

    with store.connect() as conn:
        conn.execute(
            "UPDATE merge_authorizations SET updated_at = datetime('now', '-3 minutes') "
            "WHERE pull_request_id = ?",
            (pr_id,),
        )

    merged = service.process(pr_id)

    assert merged.status == "merged"
    assert github.merged_numbers == [15]


def test_rejection_closes_pr_and_records_reflection(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)

    outcome = service.reject_merge(15, ChannelContext.local(), "/reject-merge 15")

    assert outcome.status == "rejected"
    assert github.closed_numbers == [15]
    assert store.get_pull_request(pr_id)["status"] == "closed"
    assert store.get_merge_authorization(pr_id)["decision"] == "rejected"
    assert store.list_improvement_reflections()[0]["outcome"] == "rejected"
    assert notifier.outcomes[0][1] == "rejected"


def test_external_merge_is_reflected_and_linked_to_deployment(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path)
    github.remote.update(
        {
            "state": "closed",
            "merged": True,
            "merged_at": "2026-07-17T00:00:00Z",
            "merge_commit_sha": "external-sha",
        }
    )

    outcome = service.process(pr_id)

    assert outcome.status == "merged"
    assert store.list_improvement_reflections()[0]["outcome"] == "merged"
    assert store.list_deployment_records()[0]["target_revision"] == "external-sha"
    assert notifier.outcomes[0][1] == "merged"
