from __future__ import annotations

from dataclasses import dataclass

from gugabobo.config import get_settings
from gugabobo.infra.github_client import GitHubClient
from gugabobo.memory.store import MemoryStore


class ImprovementError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImprovementCreated:
    task_id: int
    improvement_id: int


@dataclass(frozen=True)
class PullRequestOpened:
    pull_request_id: int
    number: int
    url: str
    branch_name: str


class ImprovementService:
    def __init__(self, store: MemoryStore, github_client: GitHubClient | None = None) -> None:
        self.store = store
        self.github = github_client or GitHubClient()

    def create_from_feedback(
        self,
        feedback_id: int,
        scope: str = "",
        risk_level: str = "normal",
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> ImprovementCreated:
        feedback = self.store.get_feedback(feedback_id)
        if not feedback:
            raise ImprovementError(f"feedback #{feedback_id} not found")
        settings = get_settings()
        repo = f"{settings.github_owner}/{settings.github_repo}"
        title = f"Improve from feedback #{feedback_id}"
        task_id = self.store.add_task(
            title=title,
            description=str(feedback["content"]),
            status="open",
            created_by=actor_user_id,
            assigned_skill="self_improvement",
            requires_approval=True,
        )
        improvement_id = self.store.add_improvement_task(
            task_id=task_id,
            feedback_id=feedback_id,
            repo=repo,
            scope=scope,
            risk_level=risk_level,
            approval_status="pending",
            runner_status="idle",
        )
        self.store.add_audit_log(
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            action="improvement.create",
            target=f"improvement:{improvement_id}",
            detail=f"feedback:{feedback_id}",
        )
        return ImprovementCreated(task_id=task_id, improvement_id=improvement_id)

    def approve(
        self,
        improvement_id: int,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> bool:
        return self._set_approval(improvement_id, "approved", actor_source, actor_user_id)

    def reject(
        self,
        improvement_id: int,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> bool:
        return self._set_approval(improvement_id, "rejected", actor_source, actor_user_id)

    def _set_approval(
        self,
        improvement_id: int,
        approval_status: str,
        actor_source: str,
        actor_user_id: str,
    ) -> bool:
        if not self.store.get_improvement_task(improvement_id):
            raise ImprovementError(f"improvement task #{improvement_id} not found")
        updated = self.store.update_improvement_task(
            improvement_id,
            approval_status=approval_status,
        )
        self.store.add_audit_log(
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            action=f"improvement.{approval_status}",
            target=f"improvement:{improvement_id}",
            risk_level="high",
        )
        return updated

    def open_pull_request(
        self,
        improvement_id: int,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> PullRequestOpened:
        improvement = self.store.get_improvement_task(improvement_id)
        if not improvement:
            raise ImprovementError(f"improvement task #{improvement_id} not found")
        if improvement["approval_status"] != "approved":
            raise ImprovementError("improvement task must be approved before opening a pull request")
        if not self.github.configured:
            raise ImprovementError("GUGABOBO_GITHUB_TOKEN is not configured")
        task = self.store.get_task(int(improvement["task_id"]))
        title = str(task["title"]) if task else f"Improvement #{improvement_id}"
        base_branch = self.github.get_default_branch()
        base_sha = self.github.get_branch_sha(base_branch)
        branch_name = f"gugabobo/improvement-{improvement_id}"
        self.github.create_branch(branch_name, base_sha)
        proposal = self._proposal_markdown(improvement_id, improvement, task)
        self.github.put_file(
            path=f"improvements/{improvement_id}.md",
            content=proposal,
            message=f"chore(improvement): propose #{improvement_id}",
            branch=branch_name,
        )
        pull_request = self.github.create_pull_request(
            title=title,
            head=branch_name,
            base=base_branch,
            body=proposal,
        )
        pull_request_id = self.store.add_pull_request(
            improvement_task_id=improvement_id,
            github_owner=self.github.owner,
            github_repo=self.github.repo,
            number=pull_request.number,
            url=pull_request.url,
            branch_name=branch_name,
        )
        self.store.update_improvement_task(
            improvement_id,
            runner_status="pr_open",
            branch_name=branch_name,
        )
        self.store.add_audit_log(
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            action="improvement.pr_open",
            target=f"pull_request:{pull_request.number}",
            risk_level="high",
            detail=pull_request.url,
        )
        return PullRequestOpened(
            pull_request_id=pull_request_id,
            number=pull_request.number,
            url=pull_request.url,
            branch_name=branch_name,
        )

    def _proposal_markdown(
        self,
        improvement_id: int,
        improvement: dict,
        task: dict | None,
    ) -> str:
        feedback_id = improvement.get("feedback_id", 0)
        scope = improvement.get("scope", "") or "(unspecified)"
        risk_level = improvement.get("risk_level", "normal")
        description = str(task["description"]) if task else ""
        return (
            f"# Improvement proposal #{improvement_id}\n\n"
            f"- Source feedback: #{feedback_id}\n"
            f"- Scope: {scope}\n"
            f"- Risk level: {risk_level}\n\n"
            "## Feedback\n\n"
            f"{description}\n\n"
            "## Notes\n\n"
            "This proposal was generated by gugabobo. It records the intent only; "
            "actual code changes require owner review before merge.\n"
        )
