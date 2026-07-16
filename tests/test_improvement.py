import pytest

from gugabobo.config import Settings, get_settings
from gugabobo.core.improvement import ImprovementError, ImprovementService
from gugabobo.core.notifications import OwnerNotifier
from gugabobo.infra.github_client import PullRequestResult
from gugabobo.memory.store import MemoryStore


class FakeGitHubClient:
    configured = True
    owner = "GugaBoBo-s"
    repo = "gugabobo"
    token = "token"

    def __init__(self) -> None:
        self.created_branches: list[tuple[str, str]] = []
        self.put_files: list[dict[str, str]] = []
        self.created_pulls: list[dict[str, str]] = []
        self.pull_state = {"state": "open", "merged": False, "head": {"sha": "abc"}}
        self.checks_state = "success"
        self.remote_branches: dict[str, str] = {}
        self.remote_pull: dict[str, object] = {}

    def get_pull_request(self, number):
        return self.pull_state

    def get_checks_status(self, ref):
        return self.checks_state

    def get_default_branch(self) -> str:
        return "main"

    def get_branch_sha(self, branch: str) -> str:
        return "basesha123"

    def create_branch(self, branch: str, from_sha: str) -> dict:
        self.created_branches.append((branch, from_sha))
        self.remote_branches[branch] = from_sha
        return {"ref": f"refs/heads/{branch}"}

    def put_file(self, path: str, content: str, message: str, branch: str) -> dict:
        self.put_files.append({"path": path, "content": content, "branch": branch})
        self.remote_branches[branch] = "commitsha"
        return {"commit": {"sha": "commitsha"}}

    def create_pull_request(self, title, head, base, body="") -> PullRequestResult:
        self.created_pulls.append({"title": title, "head": head, "base": base})
        self.remote_pull = {
            "number": 7,
            "html_url": "https://github.com/x/y/pull/7",
            "head": {"ref": head},
            "body": body,
        }
        return PullRequestResult(number=7, url="https://github.com/x/y/pull/7", branch_name=head)

    def find_pull_request_by_head(self, branch: str) -> dict:
        if self.remote_pull and self.remote_pull.get("head", {}).get("ref") == branch:
            return self.remote_pull
        return {}

    def try_get_branch_sha(self, branch: str) -> str:
        return self.remote_branches.get(branch, "")

    @property
    def push_url(self) -> str:
        return "https://x-access-token@github.com/GugaBoBo-s/gugabobo.git"


class UnconfiguredGitHubClient(FakeGitHubClient):
    configured = False


class FailingPullRequestGitHubClient(FakeGitHubClient):
    def create_pull_request(self, title, head, base, body="") -> PullRequestResult:
        raise RuntimeError("github unavailable")


class FakeRunner:
    def __init__(self, ok=True, output="ok", error="", configured=True):
        self._ok = ok
        self._output = output
        self._error = error
        self.configured = configured
        self.calls = []

    def run(self, prompt, cwd):
        from gugabobo.infra.claude_runner import RunResult

        self.calls.append({"prompt": prompt, "cwd": cwd})
        return RunResult(ok=self._ok, output=self._output, error=self._error)


class FakeSandbox:
    def __init__(self, diff="", tmp_path=None, checks_passed=True):
        self._diff = diff
        self._tmp_path = tmp_path
        self._checks_passed = checks_passed
        self.prepared = []
        self.committed = []
        self.pushed = []
        self.cleaned = []

    def prepare(self, improvement_id, source_repo, branch):
        self.prepared.append({"id": improvement_id, "branch": branch})
        return self._tmp_path

    def collect_diff(self, path):
        return self._diff

    def run_checks(self, path):
        from gugabobo.infra.sandbox import CheckResult

        return CheckResult(passed=self._checks_passed, output="checks output")

    def commit_all(self, path, message):
        self.committed.append(message)

    def push_branch(self, path, remote_url, branch, token):
        self.pushed.append({"remote_url": remote_url, "branch": branch, "token": token})

    def cleanup(self, improvement_id):
        self.cleaned.append(improvement_id)


class FakeNapCat:
    def __init__(self):
        self.messages = []

    def send_private_msg(self, user_id, message):
        self.messages.append((user_id, message))


class FakeTelegram:
    def send_message(self, chat_id, text):
        raise AssertionError("telegram should not be called")


def make_store_with_feedback(tmp_path) -> tuple[MemoryStore, int]:
    store = MemoryStore(tmp_path / "improve.db")
    feedback_id = store.add_feedback(source="cli", user_id="local", content="回复太长")
    return store, feedback_id


def test_store_task_improvement_and_pr_crud(tmp_path):
    store = MemoryStore(tmp_path / "crud.db")

    task_id = store.add_task(title="t1", description="desc", assigned_skill="self_improvement")
    improvement_id = store.add_improvement_task(task_id=task_id, feedback_id=3, repo="a/b")
    pr_id = store.add_pull_request(
        improvement_task_id=improvement_id,
        github_owner="a",
        github_repo="b",
        number=9,
        url="https://example/pull/9",
        branch_name="gugabobo/improvement-1",
    )
    duplicate_pr_id = store.add_pull_request(
        improvement_task_id=improvement_id,
        github_owner="a",
        github_repo="b",
        number=9,
        url="https://example/pull/9",
        branch_name="gugabobo/improvement-1",
    )

    assert store.get_task(task_id)["title"] == "t1"
    assert store.list_tasks()[0]["id"] == task_id
    assert store.update_task_status(task_id, "done") is True
    assert store.get_task(task_id)["status"] == "done"

    assert store.get_improvement_task(improvement_id)["repo"] == "a/b"
    assert store.update_improvement_task(improvement_id, approval_status="approved") is True
    assert store.get_improvement_task(improvement_id)["approval_status"] == "approved"

    assert store.get_pull_request(pr_id)["number"] == 9
    assert duplicate_pr_id == pr_id
    assert store.list_pull_requests()[0]["id"] == pr_id
    counts = {row["table"]: row["rows"] for row in store.table_counts()}
    assert counts["tasks"] == 1
    assert counts["improvement_tasks"] == 1
    assert counts["pull_requests"] == 1
    store.upsert_merge_authorization(
        pr_id,
        "approved",
        "merge_pending",
        "telegram",
        "telegram_private",
        "owner",
    )
    reflection_id = store.upsert_improvement_reflection(
        improvement_id,
        pr_id,
        "merged",
        "merged",
    )
    deployment_id = store.add_deployment_record(pr_id, "test", "abc")
    notification_id = store.queue_owner_notification(
        "pr:9:opened",
        "pr_opened",
        "telegram",
        "owner",
        "opened",
    )
    assert store.get_pull_request_by_number(9, "a", "b")["id"] == pr_id
    assert store.get_merge_authorization(pr_id)["status"] == "merge_pending"
    assert store.list_improvement_reflections()[0]["id"] == reflection_id
    assert store.list_deployment_records()[0]["id"] == deployment_id
    assert store.list_owner_notifications()[0]["id"] == notification_id


def test_create_from_feedback_creates_task_and_audit(tmp_path, monkeypatch):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    service = ImprovementService(store, github_client=FakeGitHubClient())

    result = service.create_from_feedback(feedback_id, scope="chat", risk_level="low")

    improvement = store.get_improvement_task(result.improvement_id)
    assert improvement["feedback_id"] == feedback_id
    assert improvement["approval_status"] == "pending"
    assert store.get_task(result.task_id)["assigned_skill"] == "self_improvement"
    assert store.list_audit_logs()[0]["action"] == "improvement.create"
    get_settings.cache_clear()


def test_create_from_feedback_rejects_missing_feedback(tmp_path):
    store = MemoryStore(tmp_path / "missing.db")
    service = ImprovementService(store, github_client=FakeGitHubClient())

    with pytest.raises(ImprovementError):
        service.create_from_feedback(999)


def test_open_pull_request_requires_approval(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    service = ImprovementService(store, github_client=FakeGitHubClient())
    created = service.create_from_feedback(feedback_id)

    with pytest.raises(ImprovementError):
        service.open_pull_request(created.improvement_id)
    get_settings.cache_clear()


def test_open_pull_request_creates_branch_file_and_pr(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    github = FakeGitHubClient()
    service = ImprovementService(store, github_client=github)
    created = service.create_from_feedback(feedback_id)
    service.approve(created.improvement_id)

    result = service.open_pull_request(created.improvement_id)

    assert result.number == 7
    assert github.created_branches[0][0].startswith(
        f"gugabobo/improvement-{created.improvement_id}-"
    )
    assert github.put_files[0]["path"] == f"improvements/{created.improvement_id}.md"
    assert github.created_pulls[0]["base"] == "main"
    improvement = store.get_improvement_task(created.improvement_id)
    assert improvement["runner_status"] == "pr_open"
    assert store.list_pull_requests()[0]["number"] == 7
    actions = [log["action"] for log in store.list_audit_logs()]
    assert "improvement.pr_open" in actions
    assert "improvement.approved" in actions
    get_settings.cache_clear()


def test_open_pull_request_retry_delivers_one_owner_notification(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    github = FakeGitHubClient()
    napcat = FakeNapCat()
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "improve.db",
        owner_qq_ids="10001",
        owner_telegram_ids="",
    )
    notifier = OwnerNotifier(store, settings, napcat, FakeTelegram())
    service = ImprovementService(store, github_client=github, notifier=notifier)
    created = service.create_from_feedback(feedback_id)
    service.approve(created.improvement_id)

    first = service.open_pull_request(created.improvement_id)
    second = service.open_pull_request(created.improvement_id)

    assert first.pull_request_id == second.pull_request_id
    assert len(napcat.messages) == 1
    assert len(store.list_owner_notifications()) == 1
    get_settings.cache_clear()


def test_open_pull_request_requires_configured_token(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    service = ImprovementService(store, github_client=UnconfiguredGitHubClient())
    created = service.create_from_feedback(feedback_id)
    service.approve(created.improvement_id)

    with pytest.raises(ImprovementError):
        service.open_pull_request(created.improvement_id)
    get_settings.cache_clear()


def approved_improvement(tmp_path):
    store, feedback_id = make_store_with_feedback(tmp_path)
    service = ImprovementService(store, github_client=FakeGitHubClient())
    created = service.create_from_feedback(feedback_id)
    service.approve(created.improvement_id)
    return store, service, created.improvement_id


def test_run_improvement_requires_approval(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    service = ImprovementService(store, github_client=FakeGitHubClient())
    created = service.create_from_feedback(feedback_id)

    with pytest.raises(ImprovementError):
        service.run_improvement(
            created.improvement_id,
            runner=FakeRunner(),
            sandbox=FakeSandbox(tmp_path=tmp_path),
        )
    get_settings.cache_clear()


def test_run_improvement_reports_changes_ready(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    runner = FakeRunner(ok=True)
    sandbox = FakeSandbox(diff="diff --git a/x b/x\n+change", tmp_path=tmp_path)

    outcome = service.run_improvement(improvement_id, runner=runner, sandbox=sandbox)

    assert outcome.status == "changes_ready"
    assert "change" in outcome.diff
    assert store.get_improvement_task(improvement_id)["runner_status"] == "changes_ready"
    assert store.list_audit_logs()[0]["action"] == "improvement.run"
    assert runner.calls[0]["cwd"] == tmp_path
    get_settings.cache_clear()


def test_run_improvement_reports_no_changes(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)

    outcome = service.run_improvement(
        improvement_id,
        runner=FakeRunner(ok=True),
        sandbox=FakeSandbox(diff="   \n", tmp_path=tmp_path),
    )

    assert outcome.status == "no_changes"
    assert store.get_improvement_task(improvement_id)["runner_status"] == "no_changes"
    get_settings.cache_clear()


def test_run_improvement_reports_failure(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)

    outcome = service.run_improvement(
        improvement_id,
        runner=FakeRunner(ok=False, error="claude failed"),
        sandbox=FakeSandbox(diff="ignored", tmp_path=tmp_path),
    )

    assert outcome.status == "failed"
    assert store.get_improvement_task(improvement_id)["runner_status"] == "failed"
    get_settings.cache_clear()


def test_run_improvement_requires_available_claude(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)

    with pytest.raises(ImprovementError):
        service.run_improvement(
            improvement_id,
            runner=FakeRunner(configured=False),
            sandbox=FakeSandbox(tmp_path=tmp_path),
        )
    get_settings.cache_clear()


def test_ship_opens_pull_request_when_checks_pass(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    runner = FakeRunner(ok=True)
    sandbox = FakeSandbox(diff="diff --git a/x b/x\n+change", tmp_path=tmp_path, checks_passed=True)

    outcome = service.run_and_open_pull_request(improvement_id, runner=runner, sandbox=sandbox)

    assert outcome.status == "pr_open"
    assert outcome.pr_number == 7
    assert sandbox.committed and sandbox.pushed
    assert sandbox.pushed[0]["branch"].startswith(
        f"gugabobo/improvement-{improvement_id}-"
    )
    assert sandbox.pushed[0]["token"] == "token"
    assert sandbox.cleaned == [improvement_id]
    assert store.get_improvement_task(improvement_id)["runner_status"] == "pr_open"
    assert store.list_pull_requests()[0]["number"] == 7


def test_ship_recovers_remote_pr_created_before_database_write(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    github = service.github
    branch = f"gugabobo/improvement-{improvement_id}-recovery"
    store.update_improvement_task(improvement_id, branch_name=branch)
    github.remote_pull = {
        "number": 19,
        "html_url": "https://github.com/x/y/pull/19",
        "head": {"ref": branch},
        "body": f"<!-- gugabobo-improvement:{improvement_id} -->",
    }

    outcome = service.run_and_open_pull_request(
        improvement_id,
        runner=FakeRunner(configured=False),
        sandbox=FakeSandbox(),
    )

    assert outcome.status == "pr_open"
    assert outcome.pr_number == 19
    assert store.list_pull_requests()[0]["number"] == 19


def test_ship_rejects_remote_pr_owned_by_another_improvement(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    github = service.github
    branch = f"gugabobo/improvement-{improvement_id}-stale"
    store.update_improvement_task(improvement_id, branch_name=branch)
    github.remote_pull = {
        "number": 21,
        "html_url": "https://github.com/x/y/pull/21",
        "head": {"ref": branch},
        "body": "<!-- gugabobo-improvement:999 -->",
    }
    runner = FakeRunner()

    with pytest.raises(ImprovementError, match="does not belong"):
        service.run_and_open_pull_request(
            improvement_id,
            runner=runner,
            sandbox=FakeSandbox(),
        )

    assert runner.calls == []
    assert store.list_pull_requests() == []
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("merged", "expected_status"),
    [(False, "closed"), (True, "merged")],
)
def test_ship_recovers_finished_remote_pr_state(tmp_path, merged, expected_status):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    github = service.github
    branch = f"gugabobo/improvement-{improvement_id}-finished"
    store.update_improvement_task(improvement_id, branch_name=branch)
    github.remote_pull = {
        "number": 20,
        "html_url": "https://github.com/x/y/pull/20",
        "state": "closed",
        "merged": merged,
        "merged_at": "2026-07-17T00:00:00Z" if merged else None,
        "head": {"ref": branch},
        "body": f"<!-- gugabobo-improvement:{improvement_id} -->",
    }

    outcome = service.run_and_open_pull_request(
        improvement_id,
        runner=FakeRunner(configured=False),
        sandbox=FakeSandbox(),
    )

    assert outcome.status == f"pr_{expected_status}"
    assert store.list_pull_requests()[0]["status"] == expected_status
    assert store.get_improvement_task(improvement_id)["runner_status"] == f"pr_{expected_status}"
    get_settings.cache_clear()


def test_ship_recovers_pushed_branch_before_running_again(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    github = service.github
    branch = f"gugabobo/improvement-{improvement_id}-pushed"
    store.update_improvement_task(improvement_id, branch_name=branch)
    github.remote_branches[branch] = "pushed-sha"

    outcome = service.run_and_open_pull_request(
        improvement_id,
        runner=FakeRunner(configured=False),
        sandbox=FakeSandbox(),
    )

    assert outcome.status == "pr_open"
    assert github.created_pulls[0]["head"] == branch
    assert store.list_pull_requests()[0]["number"] == 7
    actions = [log["action"] for log in store.list_audit_logs()]
    assert "improvement.pr_open" in actions
    get_settings.cache_clear()


def test_ship_stops_when_remote_branch_cannot_be_recovered(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    github = FailingPullRequestGitHubClient()
    service = ImprovementService(store, github_client=github)
    created = service.create_from_feedback(feedback_id)
    service.approve(created.improvement_id)
    branch = f"gugabobo/improvement-{created.improvement_id}-pushed"
    store.update_improvement_task(created.improvement_id, branch_name=branch)
    github.remote_branches[branch] = "pushed-sha"
    runner = FakeRunner()

    with pytest.raises(ImprovementError, match="pull request recovery failed"):
        service.run_and_open_pull_request(
            created.improvement_id,
            runner=runner,
            sandbox=FakeSandbox(),
        )

    assert runner.calls == []
    get_settings.cache_clear()


def test_ship_stops_when_checks_fail(tmp_path):
    get_settings.cache_clear()
    store, service, improvement_id = approved_improvement(tmp_path)
    sandbox = FakeSandbox(diff="diff --git a/x b/x\n+change", tmp_path=tmp_path, checks_passed=False)

    outcome = service.run_and_open_pull_request(
        improvement_id,
        runner=FakeRunner(ok=True),
        sandbox=sandbox,
    )

    assert outcome.status == "checks_failed"
    assert not sandbox.committed
    assert not sandbox.pushed
    assert store.get_improvement_task(improvement_id)["runner_status"] == "checks_failed"
    assert store.list_pull_requests() == []
    get_settings.cache_clear()


def test_ship_requires_configured_github(tmp_path):
    get_settings.cache_clear()
    store, feedback_id = make_store_with_feedback(tmp_path)
    service = ImprovementService(store, github_client=UnconfiguredGitHubClient())
    created = service.create_from_feedback(feedback_id)
    service.approve(created.improvement_id)

    with pytest.raises(ImprovementError):
        service.run_and_open_pull_request(
            created.improvement_id,
            runner=FakeRunner(),
            sandbox=FakeSandbox(diff="x", tmp_path=tmp_path),
        )
    get_settings.cache_clear()


def test_sync_pull_request_updates_open_and_checks(tmp_path):
    get_settings.cache_clear()
    store = MemoryStore(tmp_path / "sync.db")
    github = FakeGitHubClient()
    github.pull_state = {"state": "open", "merged": False, "head": {"sha": "abc"}}
    github.checks_state = "success"
    pr_id = store.add_pull_request(
        improvement_task_id=1,
        github_owner="GugaBoBo-s",
        github_repo="gugabobo",
        number=7,
        url="https://github.com/x/y/pull/7",
        branch_name="gugabobo/improvement-1",
    )
    service = ImprovementService(store, github_client=github)

    status = service.sync_pull_request(pr_id)

    assert status.status == "open"
    assert status.checks_status == "success"
    stored = store.get_pull_request(pr_id)
    assert stored["status"] == "open"
    assert stored["checks_status"] == "success"
    assert store.list_audit_logs()[0]["action"] == "improvement.pr_sync"
    get_settings.cache_clear()


def test_sync_pull_request_marks_merged(tmp_path):
    get_settings.cache_clear()
    store = MemoryStore(tmp_path / "sync2.db")
    github = FakeGitHubClient()
    github.pull_state = {
        "state": "closed",
        "merged": True,
        "merged_at": "2026-07-09T10:00:00Z",
        "head": {"sha": "def"},
    }
    github.checks_state = "success"
    pr_id = store.add_pull_request(
        improvement_task_id=1,
        github_owner="GugaBoBo-s",
        github_repo="gugabobo",
        number=8,
        url="https://github.com/x/y/pull/8",
        branch_name="gugabobo/improvement-1",
    )
    service = ImprovementService(store, github_client=github)

    status = service.sync_pull_request(pr_id)

    assert status.status == "merged"
    assert status.merged_at == "2026-07-09T10:00:00Z"
    assert store.get_pull_request(pr_id)["merged_at"] == "2026-07-09T10:00:00Z"
    get_settings.cache_clear()


def test_sync_pull_request_rejects_missing(tmp_path):
    get_settings.cache_clear()
    store = MemoryStore(tmp_path / "sync3.db")
    service = ImprovementService(store, github_client=FakeGitHubClient())

    with pytest.raises(ImprovementError):
        service.sync_pull_request(999)
    get_settings.cache_clear()


def test_sync_pull_request_requires_github(tmp_path):
    get_settings.cache_clear()
    store = MemoryStore(tmp_path / "sync4.db")
    pr_id = store.add_pull_request(
        improvement_task_id=1,
        github_owner="GugaBoBo-s",
        github_repo="gugabobo",
        number=9,
        url="https://github.com/x/y/pull/9",
        branch_name="b",
    )
    service = ImprovementService(store, github_client=UnconfiguredGitHubClient())

    with pytest.raises(ImprovementError):
        service.sync_pull_request(pr_id)
    get_settings.cache_clear()
