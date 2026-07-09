import pytest

from gugabobo.core.improvement import ImprovementError, ImprovementService
from gugabobo.config import get_settings
from gugabobo.infra.github_client import PullRequestResult
from gugabobo.memory.store import MemoryStore


class FakeGitHubClient:
    configured = True
    owner = "GugaBoBo-s"
    repo = "gugabobo"

    def __init__(self) -> None:
        self.created_branches: list[tuple[str, str]] = []
        self.put_files: list[dict[str, str]] = []
        self.created_pulls: list[dict[str, str]] = []

    def get_default_branch(self) -> str:
        return "main"

    def get_branch_sha(self, branch: str) -> str:
        return "basesha123"

    def create_branch(self, branch: str, from_sha: str) -> dict:
        self.created_branches.append((branch, from_sha))
        return {"ref": f"refs/heads/{branch}"}

    def put_file(self, path: str, content: str, message: str, branch: str) -> dict:
        self.put_files.append({"path": path, "content": content, "branch": branch})
        return {"commit": {"sha": "commitsha"}}

    def create_pull_request(self, title, head, base, body="") -> PullRequestResult:
        self.created_pulls.append({"title": title, "head": head, "base": base})
        return PullRequestResult(number=7, url="https://github.com/x/y/pull/7", branch_name=head)


class UnconfiguredGitHubClient(FakeGitHubClient):
    configured = False


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

    assert store.get_task(task_id)["title"] == "t1"
    assert store.list_tasks()[0]["id"] == task_id
    assert store.update_task_status(task_id, "done") is True
    assert store.get_task(task_id)["status"] == "done"

    assert store.get_improvement_task(improvement_id)["repo"] == "a/b"
    assert store.update_improvement_task(improvement_id, approval_status="approved") is True
    assert store.get_improvement_task(improvement_id)["approval_status"] == "approved"

    assert store.get_pull_request(pr_id)["number"] == 9
    assert store.list_pull_requests()[0]["id"] == pr_id
    counts = {row["table"]: row["rows"] for row in store.table_counts()}
    assert counts["tasks"] == 1
    assert counts["improvement_tasks"] == 1
    assert counts["pull_requests"] == 1


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
    assert github.created_branches[0][0] == f"gugabobo/improvement-{created.improvement_id}"
    assert github.put_files[0]["path"] == f"improvements/{created.improvement_id}.md"
    assert github.created_pulls[0]["base"] == "main"
    improvement = store.get_improvement_task(created.improvement_id)
    assert improvement["runner_status"] == "pr_open"
    assert store.list_pull_requests()[0]["number"] == 7
    actions = [log["action"] for log in store.list_audit_logs()]
    assert "improvement.pr_open" in actions
    assert "improvement.approved" in actions
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
