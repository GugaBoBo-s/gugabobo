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
        self.remote = {
            "state": "open",
            "merged": False,
            "merged_at": None,
            "merge_commit_sha": "",
            "head": {"sha": "head-sha"},
        }
        self.merged_numbers: list[int] = []
        self.closed_numbers: list[int] = []

    def get_pull_request(self, number: int) -> dict[str, object]:
        return self.remote

    def get_checks_status(self, ref: str) -> str:
        assert ref == "head-sha"
        return self.checks_status

    def merge_pull_request(
        self,
        number: int,
        commit_title: str,
        merge_method: str = "squash",
    ) -> MergeResult:
        self.merged_numbers.append(number)
        return MergeResult(merged=True, sha="merge-sha", message="merged")

    def close_pull_request(self, number: int) -> dict[str, object]:
        self.closed_numbers.append(number)
        self.remote["state"] = "closed"
        return self.remote


class FakeNotifier:
    def __init__(self) -> None:
        self.outcomes: list[tuple[int, str, str]] = []
        self.blocked: list[tuple[int, str, str]] = []

    def notify_pr_outcome(self, number: int, outcome: str, detail: str) -> list[int]:
        self.outcomes.append((number, outcome, detail))
        return []

    def retry_pending(self, limit: int = 50) -> dict[str, int]:
        return {"attempted": 0, "sent": 0}

    def notify_pr_blocked(self, number: int, reason: str, url: str) -> list[int]:
        self.blocked.append((number, reason, url))
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
    assert parse_merge_command("聊聊 PR 15") is None


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
    assert store.get_pull_request(pr_id)["status"] == "merged"
    assert store.get_merge_authorization(pr_id)["status"] == "merged"
    assert store.list_improvement_reflections()[0]["outcome"] == "merged"
    assert store.list_deployment_records()[0]["target_revision"] == "merge-sha"
    assert notifier.outcomes[0][1] == "merged"


def test_approval_waits_for_checks_then_daemon_merges(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path, "pending")

    outcome = service.approve_merge(15, ChannelContext.local(), "/merge 15")

    assert outcome.status == "waiting_checks"
    assert store.get_merge_authorization(pr_id)["status"] == "waiting_checks"
    assert github.merged_numbers == []

    github.checks_status = "success"
    tick = service.tick()

    assert tick["merged"] == 1
    assert github.merged_numbers == [15]
    assert store.get_merge_authorization(pr_id)["status"] == "merged"


def test_unknown_checks_never_merge(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path, "unknown")

    outcome = service.approve_merge(15, ChannelContext.local(), "/merge 15")

    assert outcome.status == "waiting_checks"
    assert "Checks: Read" in outcome.message
    assert github.merged_numbers == []
    assert store.get_pull_request(pr_id)["status"] == "open"


def test_failed_checks_record_reason_and_notify_owner(tmp_path) -> None:
    store, pr_id, github, notifier, service = build_service(tmp_path, "failure")

    outcome = service.approve_merge(15, ChannelContext.local(), "/merge 15")

    assert outcome.status == "checks_failed"
    assert github.merged_numbers == []
    reflection = store.list_improvement_reflections()[0]
    assert reflection["outcome"] == "checks_failed"
    assert "GitHub checks reported failure" in reflection["lessons"]
    assert notifier.blocked[0][0] == 15


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
