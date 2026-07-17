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


def test_auto_deploy_validates_before_activation_and_supports_rollback() -> None:
    script = (Path(__file__).parents[1] / "deploy" / "auto-deploy.sh").read_text(
        encoding="utf-8"
    )

    validation = script.index("write_status \"validating\"")
    activation = script.index("write_status \"deploying\"")
    assert validation < activation
    assert 'BRANCH="main"' in script
    assert "merge-base --is-ancestor" in script
    assert "merge --ff-only" in script
    assert "reset --hard" in script
    assert "health_check" in script
    assert "deploy-failed-target" in script
    assert "commits/{revision}/pulls" in script
    assert "/actions/runs" in script
    assert 'run.get("name") == "CI"' in script
    assert 'job.get("name") == "test"' in script
    assert "check-runs" not in script
    assert "verify_pending_deployment" in script
    assert "deployment_records.pull_request_id" in script
    assert 'str(pull.get("number")) == pull_request_number' in script
    assert "mark_pending_deployment_failed" in script
    assert "read_env_value GUGABOBO_AUTO_DEPLOY_ENABLED" in script
    assert "read_env_value GUGABOBO_GITHUB_TOKEN" in script
    assert 'if deployment_reference=$(verify_pending_deployment "$db_path"); then' in script
    assert 'if verify_github_target "$github_token"' in script


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


def test_failed_deployment_report_updates_matching_pending_revision(tmp_path) -> None:
    store = MemoryStore(tmp_path / "deployment-failed.db")
    task_id = store.add_task(title="deploy")
    improvement_id = store.add_improvement_task(task_id=task_id)
    pr_id = store.add_pull_request(
        improvement_task_id=improvement_id,
        github_owner="owner",
        github_repo="repo",
        number=2,
        url="https://example/pull/2",
        branch_name="change",
    )
    store.add_deployment_record(pr_id, "test", "abc123")
    settings = Settings(
        env="test",
        data_dir=tmp_path,
        db_path=tmp_path / "deployment-failed.db",
    )

    outcome = DeploymentService(store, settings).report(
        "abc123",
        "failed",
        "health check failed",
        current_revision="previous456",
    )

    assert outcome.updated == 1
    record = store.list_deployment_records()[0]
    assert record["status"] == "failed"
    assert record["detail"] == "health check failed"
    assert record["deployed_revision"] == "previous456"
