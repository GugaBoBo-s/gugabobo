import subprocess
from pathlib import Path

from gugabobo.config import Settings
from gugabobo.core.deployment import DeploymentService
from gugabobo.memory.store import MemoryStore


def test_runner_dockerfile_uses_supported_node_runtime() -> None:
    dockerfile = (
        Path(__file__).parents[1] / "deploy" / "Dockerfile.runner"
    ).read_text(encoding="utf-8")

    assert "FROM node:22-bookworm-slim AS node-runtime" in dockerfile
    assert "apt-get install -y --no-install-recommends git nodejs npm" not in dockerfile


def git(repo, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_current_deployment_marks_ancestor_revision(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    tracked = repo / "tracked.txt"
    tracked.write_text("one", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "first")
    target = git(repo, "rev-parse", "HEAD")
    tracked.write_text("two", encoding="utf-8")
    git(repo, "commit", "-am", "second")
    current = git(repo, "rev-parse", "HEAD")

    store = MemoryStore(tmp_path / "deployment.db")
    task_id = store.add_task(title="deploy")
    improvement_id = store.add_improvement_task(task_id=task_id)
    pr_id = store.add_pull_request(
        improvement_task_id=improvement_id,
        github_owner="owner",
        github_repo="repo",
        number=1,
        url="https://example/pull/1",
        branch_name="change",
    )
    deployment_id = store.add_deployment_record(pr_id, "test", target)
    settings = Settings(
        env="test",
        data_dir=tmp_path,
        db_path=tmp_path / "deployment.db",
    )

    outcome = DeploymentService(store, settings).record_current(repo)

    assert outcome.current_revision == current
    assert outcome.deployed == 1
    record = store.list_deployment_records()[0]
    assert record["id"] == deployment_id
    assert record["status"] == "deployed"
    assert record["deployed_revision"] == current
