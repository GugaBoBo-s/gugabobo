from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import get_settings
from gugabobo.infra.claude_runner import ClaudeCodeRunner
from gugabobo.infra.github_client import GitHubClient
from gugabobo.infra.sandbox import SandboxManager
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


@dataclass(frozen=True)
class RunOutcome:
    status: str
    branch_name: str
    diff: str = ""
    detail: str = ""
    pr_number: int | None = None
    pr_url: str = ""


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

    def run_improvement(
        self,
        improvement_id: int,
        runner: ClaudeCodeRunner | None = None,
        sandbox: SandboxManager | None = None,
        source_repo: Path | None = None,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> RunOutcome:
        improvement = self.store.get_improvement_task(improvement_id)
        if not improvement:
            raise ImprovementError(f"improvement task #{improvement_id} not found")
        if improvement["approval_status"] != "approved":
            raise ImprovementError("improvement task must be approved before running")
        runner = runner or ClaudeCodeRunner()
        sandbox = sandbox or SandboxManager()
        if not runner.configured:
            raise ImprovementError("Claude Code (claude) is not available on this machine")
        task = self.store.get_task(int(improvement["task_id"]))
        branch_name = f"gugabobo/improvement-{improvement_id}"
        self.store.update_improvement_task(improvement_id, runner_status="running")
        try:
            path = sandbox.prepare(
                improvement_id,
                source_repo or Path.cwd(),
                branch_name,
            )
        except Exception as error:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            raise ImprovementError(f"sandbox preparation failed: {error}") from error
        prompt = self._build_prompt(improvement, task)
        result = runner.run(prompt, cwd=path)
        if not result.ok:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            self._audit_run(actor_source, actor_user_id, improvement_id, "failed", result.error)
            return RunOutcome(status="failed", branch_name=branch_name, detail=result.error[:500])
        diff = sandbox.collect_diff(path)
        if not diff.strip():
            self.store.update_improvement_task(improvement_id, runner_status="no_changes")
            self._audit_run(actor_source, actor_user_id, improvement_id, "no_changes", "")
            return RunOutcome(status="no_changes", branch_name=branch_name)
        self.store.update_improvement_task(
            improvement_id,
            runner_status="changes_ready",
            branch_name=branch_name,
        )
        self._audit_run(
            actor_source,
            actor_user_id,
            improvement_id,
            "changes_ready",
            f"diff {len(diff)} chars",
        )
        return RunOutcome(status="changes_ready", branch_name=branch_name, diff=diff)

    def run_and_open_pull_request(
        self,
        improvement_id: int,
        runner: ClaudeCodeRunner | None = None,
        sandbox: SandboxManager | None = None,
        source_repo: Path | None = None,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> RunOutcome:
        improvement = self.store.get_improvement_task(improvement_id)
        if not improvement:
            raise ImprovementError(f"improvement task #{improvement_id} not found")
        if improvement["approval_status"] != "approved":
            raise ImprovementError("improvement task must be approved before running")
        runner = runner or ClaudeCodeRunner()
        sandbox = sandbox or SandboxManager()
        if not runner.configured:
            raise ImprovementError("Claude Code (claude) is not available on this machine")
        if not self.github.configured:
            raise ImprovementError("GUGABOBO_GITHUB_TOKEN is not configured")
        task = self.store.get_task(int(improvement["task_id"]))
        title = str(task["title"]) if task else f"Improvement #{improvement_id}"
        branch_name = f"gugabobo/improvement-{improvement_id}"
        self.store.update_improvement_task(improvement_id, runner_status="running")
        try:
            path = sandbox.prepare(improvement_id, source_repo or Path.cwd(), branch_name)
        except Exception as error:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            raise ImprovementError(f"sandbox preparation failed: {error}") from error
        result = runner.run(self._build_prompt(improvement, task), cwd=path)
        if not result.ok:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            self._audit_run(actor_source, actor_user_id, improvement_id, "failed", result.error)
            return RunOutcome(status="failed", branch_name=branch_name, detail=result.error[:500])
        diff = sandbox.collect_diff(path)
        if not diff.strip():
            self.store.update_improvement_task(improvement_id, runner_status="no_changes")
            self._audit_run(actor_source, actor_user_id, improvement_id, "no_changes", "")
            return RunOutcome(status="no_changes", branch_name=branch_name)
        checks = sandbox.run_checks(path)
        if not checks.passed:
            self.store.update_improvement_task(
                improvement_id,
                runner_status="checks_failed",
                branch_name=branch_name,
            )
            self._audit_run(
                actor_source,
                actor_user_id,
                improvement_id,
                "checks_failed",
                checks.output[-500:],
            )
            return RunOutcome(
                status="checks_failed",
                branch_name=branch_name,
                diff=diff,
                detail=checks.output[-2000:],
            )
        sandbox.commit_all(path, f"feat(improvement): #{improvement_id} via Claude Code")
        sandbox.push_branch(path, self.github.push_url, branch_name)
        base_branch = self.github.get_default_branch()
        pull_request = self.github.create_pull_request(
            title=title,
            head=branch_name,
            base=base_branch,
            body=self._proposal_markdown(improvement_id, improvement, task),
        )
        self.store.add_pull_request(
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
        sandbox.cleanup(improvement_id)
        return RunOutcome(
            status="pr_open",
            branch_name=branch_name,
            diff=diff,
            pr_number=pull_request.number,
            pr_url=pull_request.url,
        )

    def _audit_run(
        self,
        actor_source: str,
        actor_user_id: str,
        improvement_id: int,
        status: str,
        detail: str,
    ) -> None:
        self.store.add_audit_log(
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            action="improvement.run",
            target=f"improvement:{improvement_id}",
            status=status,
            risk_level="high",
            detail=detail[:1000],
        )

    def _build_prompt(self, improvement: dict, task: dict | None) -> str:
        description = str(task["description"]) if task else ""
        scope = improvement.get("scope", "") or "(unspecified)"
        return (
            "You are gugabobo's self-improvement runner working inside a sandboxed "
            "clone of the repository. Implement the following improvement request by "
            "editing the code directly. Keep the change minimal and aligned with the "
            "existing style, and do not commit or push.\n\n"
            f"Scope hint: {scope}\n\n"
            f"Improvement request (from user feedback):\n{description}\n"
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
