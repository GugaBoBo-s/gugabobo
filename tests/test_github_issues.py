import json
from pathlib import Path

from gugabobo.config import Settings
from gugabobo.core.github_issues import GitHubIssueAutomationService
from gugabobo.core.improvement import ImprovementCreated, RunOutcome
from gugabobo.infra.code_models import CodeModelResult
from gugabobo.memory.store import MemoryStore


class FakeOrganizationClient:
    configured = True

    def list_organization_repositories(self, organization):
        assert organization == "GugaBoBo-s"
        return [{"name": "gugabobo", "owner": {"login": "GugaBoBo-s"}}]


class FakeRepositoryClient:
    configured = True
    owner = "GugaBoBo-s"
    repo = "gugabobo"

    def __init__(self, issues):
        self.issues = issues
        self.linked_pull_request = False

    def list_issues(self, state="open", limit=None):
        assert state == "open"
        return self.issues[:limit]

    def has_open_linked_pull_request(self, issue_number):
        return self.linked_pull_request


class FakeCodeModel:
    configured = True

    def __init__(self, worthwhile=True, confidence=0.9):
        self.worthwhile = worthwhile
        self.confidence = confidence
        self.calls = []

    def complete_with_metadata(self, messages, temperature=0.0):
        self.calls.append(messages)
        return CodeModelResult(
            json.dumps(
                {
                    "worthwhile": self.worthwhile,
                    "confidence": self.confidence,
                    "rationale": "bounded bug with a reproducible failure",
                    "implementation_summary": "fix the parser and add a regression test",
                }
            ),
            "claude",
            "claude-code",
        )


class FakeImprovementService:
    def __init__(self):
        self.created = []
        self.shipped = []

    def create_from_github_issue(self, owner, repo, number, title, body, url):
        self.created.append((owner, repo, number, title, body, url))
        return ImprovementCreated(task_id=11, improvement_id=12)

    def run_and_open_pull_request(self, improvement_id, **kwargs):
        self.shipped.append((improvement_id, kwargs))
        return RunOutcome(
            status="pr_open",
            branch_name="gugabobo/improvement-12",
            pr_number=21,
            pr_url="https://github.com/GugaBoBo-s/gugabobo/pull/21",
        )


def issue(updated_at="2026-07-17T00:00:00Z"):
    return {
        "number": 7,
        "html_url": "https://github.com/GugaBoBo-s/gugabobo/issues/7",
        "updated_at": updated_at,
        "title": "Parser loses escaped values",
        "body": "Reproduction and expected behavior",
        "labels": [{"name": "bug"}],
    }


def settings(tmp_path: Path, **overrides):
    values = {
        "db_path": tmp_path / "issues.db",
        "github_token": "token",
        "github_issue_enabled": True,
        "github_organization": "GugaBoBo-s",
        "github_owner": "GugaBoBo-s",
        "github_repo": "gugabobo",
        "claude_auth_token": "claude-token",
    }
    values.update(overrides)
    return Settings(**values)


def build_service(tmp_path, repository, model, improvement, **overrides):
    config = settings(tmp_path, **overrides)
    return GitHubIssueAutomationService(
        MemoryStore(config.db_path),
        config,
        organization_client=FakeOrganizationClient(),
        github_factory=lambda owner, repo: repository,
        code_model=model,
        improvement_factory=lambda github: improvement,
    )


def test_worthwhile_issue_is_implemented_once_and_linked_to_pr(tmp_path):
    repository = FakeRepositoryClient([issue()])
    model = FakeCodeModel()
    improvement = FakeImprovementService()
    service = build_service(tmp_path, repository, model, improvement)

    first = service.tick()
    second = service.tick()
    record = service.store.list_github_issue_runs()[0]

    assert first["pull_requests"] == 1
    assert second["skipped"] == 1
    assert len(model.calls) == 1
    assert len(improvement.created) == 1
    assert improvement.shipped[0][1]["clone_remote"] is True
    assert record["status"] == "pr_open"
    assert record["improvement_task_id"] == 12
    assert record["pr_number"] == 21


def test_low_confidence_issue_is_recorded_without_modifying_repository(tmp_path):
    model = FakeCodeModel(worthwhile=True, confidence=0.5)
    improvement = FakeImprovementService()
    service = build_service(
        tmp_path,
        FakeRepositoryClient([issue()]),
        model,
        improvement,
        github_issue_min_confidence=0.75,
    )

    result = service.tick()
    record = service.store.list_github_issue_runs()[0]

    assert result["evaluated"] == 1
    assert improvement.created == []
    assert record["status"] == "below_confidence"
    assert record["worthwhile"] == 1


def test_issue_outside_auto_fix_allowlist_keeps_worthwhile_decision(tmp_path):
    improvement = FakeImprovementService()
    service = build_service(
        tmp_path,
        FakeRepositoryClient([issue()]),
        FakeCodeModel(),
        improvement,
        github_issue_auto_fix_repositories="GugaBoBo-s/another-repo",
    )

    result = service.tick()
    record = service.store.list_github_issue_runs()[0]

    assert result["worthwhile"] == 1
    assert improvement.created == []
    assert record["status"] == "worthwhile"


def test_updated_issue_creates_a_new_evaluation_run(tmp_path):
    repository = FakeRepositoryClient([issue()])
    model = FakeCodeModel(worthwhile=False)
    service = build_service(tmp_path, repository, model, FakeImprovementService())

    service.tick()
    repository.issues = [issue("2026-07-17T01:00:00Z")]
    service.tick()

    assert len(model.calls) == 2
    assert len(service.store.list_github_issue_runs()) == 2
    assert "untrusted data" in model.calls[0][0]["content"]


def test_issue_with_linked_open_pull_request_is_not_evaluated(tmp_path):
    repository = FakeRepositoryClient([issue()])
    repository.linked_pull_request = True
    model = FakeCodeModel()
    service = build_service(tmp_path, repository, model, FakeImprovementService())

    result = service.tick()
    record = service.store.list_github_issue_runs()[0]

    assert result["evaluated"] == 1
    assert model.calls == []
    assert record["status"] == "linked_pull_request"
