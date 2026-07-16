from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from gugabobo.config import get_settings
from gugabobo.core.notifications import OwnerNotifier
from gugabobo.infra.claude_runner import ClaudeCodeRunner
from gugabobo.infra.github_client import GitHubClient, PullRequestResult
from gugabobo.infra.redaction import redact_sensitive
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
    status: str = "open"


@dataclass(frozen=True)
class RunOutcome:
    status: str
    branch_name: str
    diff: str = ""
    detail: str = ""
    pr_number: int | None = None
    pr_url: str = ""


@dataclass(frozen=True)
class PullRequestStatus:
    pull_request_id: int
    number: int
    status: str
    checks_status: str
    merged_at: str = ""


class ImprovementService:
    def __init__(
        self,
        store: MemoryStore,
        github_client: GitHubClient | None = None,
        notifier: OwnerNotifier | None = None,
    ) -> None:
        self.store = store
        self.github = github_client or GitHubClient()
        self.notifier = notifier or OwnerNotifier(store)

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
        existing = self.store.get_pull_request_for_improvement(improvement_id)
        if existing:
            return self._tracked_pull_request(existing, title)
        proposal = self._proposal_markdown(improvement_id, improvement, task)
        branch_name = self._branch_name(improvement_id, improvement)
        self.store.update_improvement_task(improvement_id, branch_name=branch_name)
        base_branch = self.github.get_default_branch()
        base_sha = self.github.get_branch_sha(base_branch)
        recovered = self._recover_pull_request(
            improvement_id,
            branch_name,
            base_branch,
            base_sha,
            title,
            proposal,
            actor_source,
            actor_user_id,
        )
        if recovered:
            return recovered
        branch_sha = self.github.try_get_branch_sha(branch_name)
        if not branch_sha:
            self.github.create_branch(branch_name, base_sha)
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
        return self._persist_pull_request(
            improvement_id,
            pull_request,
            title,
            actor_source,
            actor_user_id,
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
            raise ImprovementError("isolated Claude Code runner is not available")
        task = self.store.get_task(int(improvement["task_id"]))
        branch_name = self._branch_name(improvement_id, improvement)
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
        try:
            result = runner.run(prompt, cwd=path)
            if not result.ok:
                raise ImprovementError(result.error or "Claude Code runner failed")
            diff = sandbox.collect_diff(path)
        except Exception as error:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            detail = self._safe_error(error)
            self._audit_run(actor_source, actor_user_id, improvement_id, "failed", detail)
            return RunOutcome(status="failed", branch_name=branch_name, detail=detail[:500])
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
        if not self.github.configured:
            raise ImprovementError("GUGABOBO_GITHUB_TOKEN is not configured")
        task = self.store.get_task(int(improvement["task_id"]))
        title = str(task["title"]) if task else f"Improvement #{improvement_id}"
        proposal = self._proposal_markdown(improvement_id, improvement, task)
        branch_name = self._branch_name(improvement_id, improvement)
        self.store.update_improvement_task(improvement_id, branch_name=branch_name)
        existing = self.store.get_pull_request_for_improvement(improvement_id)
        if existing:
            tracked = self._tracked_pull_request(existing, title)
            return RunOutcome(
                status=f"pr_{tracked.status}",
                branch_name=tracked.branch_name,
                pr_number=tracked.number,
                pr_url=tracked.url,
            )
        base_branch = self.github.get_default_branch()
        base_sha = self.github.get_branch_sha(base_branch)
        recovered = self._recover_pull_request(
            improvement_id,
            branch_name,
            base_branch,
            base_sha,
            title,
            proposal,
            actor_source,
            actor_user_id,
        )
        if recovered:
            return RunOutcome(
                status=f"pr_{recovered.status}",
                branch_name=recovered.branch_name,
                pr_number=recovered.number,
                pr_url=recovered.url,
            )
        runner = runner or ClaudeCodeRunner()
        sandbox = sandbox or SandboxManager()
        if not runner.configured:
            raise ImprovementError("isolated Claude Code runner is not available")
        self.store.update_improvement_task(
            improvement_id,
            runner_status="running",
            branch_name=branch_name,
        )
        try:
            path = sandbox.prepare(improvement_id, source_repo or Path.cwd(), branch_name)
        except Exception as error:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            raise ImprovementError(f"sandbox preparation failed: {error}") from error
        try:
            result = runner.run(self._build_prompt(improvement, task), cwd=path)
            if not result.ok:
                raise ImprovementError(result.error or "Claude Code runner failed")
            diff = sandbox.collect_diff(path)
        except Exception as error:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            detail = self._safe_error(error)
            self._audit_run(actor_source, actor_user_id, improvement_id, "failed", detail)
            return RunOutcome(status="failed", branch_name=branch_name, detail=detail[:500])
        if not diff.strip():
            self.store.update_improvement_task(improvement_id, runner_status="no_changes")
            self._audit_run(actor_source, actor_user_id, improvement_id, "no_changes", "")
            return RunOutcome(status="no_changes", branch_name=branch_name)
        try:
            checks = sandbox.run_checks(path)
        except Exception as error:
            self.store.update_improvement_task(improvement_id, runner_status="failed")
            detail = self._safe_error(error)
            self._audit_run(actor_source, actor_user_id, improvement_id, "failed", detail)
            return RunOutcome(status="failed", branch_name=branch_name, diff=diff, detail=detail)
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
        try:
            sandbox.commit_all(path, f"feat(improvement): #{improvement_id} via Claude Code")
            sandbox.push_branch(path, self.github.push_url, branch_name, self.github.token)
            pull_request = self.github.create_pull_request(
                title=title,
                head=branch_name,
                base=base_branch,
                body=proposal,
            )
        except Exception as error:
            remote = self.github.find_pull_request_by_head(branch_name)
            if remote:
                recovered = self._persist_pull_request(
                    improvement_id,
                    self._pull_request_result(remote, branch_name),
                    title,
                    actor_source,
                    actor_user_id,
                )
                sandbox.cleanup(improvement_id)
                return RunOutcome(
                    status=f"pr_{recovered.status}",
                    branch_name=recovered.branch_name,
                    diff=diff,
                    pr_number=recovered.number,
                    pr_url=recovered.url,
                )
            self.store.update_improvement_task(
                improvement_id,
                runner_status="failed",
                branch_name=branch_name,
            )
            detail = self._safe_error(error)
            self._audit_run(actor_source, actor_user_id, improvement_id, "failed", detail)
            return RunOutcome(status="failed", branch_name=branch_name, diff=diff, detail=detail)
        opened = self._persist_pull_request(
            improvement_id,
            pull_request,
            title,
            actor_source,
            actor_user_id,
        )
        sandbox.cleanup(improvement_id)
        return RunOutcome(
            status=f"pr_{opened.status}",
            branch_name=opened.branch_name,
            diff=diff,
            pr_number=opened.number,
            pr_url=opened.url,
        )

    def sync_pull_request(
        self,
        pull_request_id: int,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> PullRequestStatus:
        record = self.store.get_pull_request(pull_request_id)
        if not record:
            raise ImprovementError(f"pull request #{pull_request_id} not found")
        if not self.github.configured:
            raise ImprovementError("GUGABOBO_GITHUB_TOKEN is not configured")
        number = int(record["number"])
        owner = str(record["github_owner"])
        repo = str(record["github_repo"])
        if self.github.owner == owner and self.github.repo == repo:
            github = self.github
        else:
            github = GitHubClient(self.github.settings, owner=owner, repo=repo)
        remote = github.get_pull_request(number)
        merged = bool(remote.get("merged"))
        state = str(remote.get("state", ""))
        status = "merged" if merged else ("closed" if state == "closed" else "open")
        merged_at = remote.get("merged_at")
        head_sha = str(remote.get("head", {}).get("sha", ""))
        checks_status = "unknown"
        if head_sha:
            checks_status = github.get_checks_status(head_sha)
        self.store.update_pull_request(
            pull_request_id,
            status=status,
            checks_status=checks_status,
            merged_at=merged_at,
        )
        self.store.add_audit_log(
            actor_source=actor_source,
            actor_user_id=actor_user_id,
            action="improvement.pr_sync",
            target=f"pull_request:{number}",
            detail=f"{status}/{checks_status}",
        )
        return PullRequestStatus(
            pull_request_id=pull_request_id,
            number=number,
            status=status,
            checks_status=checks_status,
            merged_at=str(merged_at or ""),
        )

    def _recover_pull_request(
        self,
        improvement_id: int,
        branch_name: str,
        base_branch: str,
        base_sha: str,
        title: str,
        body: str,
        actor_source: str,
        actor_user_id: str,
    ) -> PullRequestOpened | None:
        remote = self.github.find_pull_request_by_head(branch_name)
        if remote:
            self._require_improvement_marker(remote, improvement_id)
            return self._persist_pull_request(
                improvement_id,
                self._pull_request_result(remote, branch_name),
                title,
                actor_source,
                actor_user_id,
            )
        branch_sha = self.github.try_get_branch_sha(branch_name)
        if not branch_sha or branch_sha == base_sha:
            return None
        try:
            pull_request = self.github.create_pull_request(
                title=title,
                head=branch_name,
                base=base_branch,
                body=body,
            )
        except Exception as error:
            remote = self.github.find_pull_request_by_head(branch_name)
            if not remote:
                detail = self._safe_error(error)
                raise ImprovementError(
                    f"remote branch exists but pull request recovery failed: {detail}"
                ) from error
            self._require_improvement_marker(remote, improvement_id)
            pull_request = self._pull_request_result(remote, branch_name)
        return self._persist_pull_request(
            improvement_id,
            pull_request,
            title,
            actor_source,
            actor_user_id,
        )

    def _persist_pull_request(
        self,
        improvement_id: int,
        pull_request: PullRequestResult,
        title: str,
        actor_source: str,
        actor_user_id: str,
    ) -> PullRequestOpened:
        existing = self.store.get_pull_request_for_improvement(improvement_id)
        pull_request_id = self.store.add_pull_request(
            improvement_task_id=improvement_id,
            github_owner=self.github.owner,
            github_repo=self.github.repo,
            number=pull_request.number,
            url=pull_request.url,
            branch_name=pull_request.branch_name,
            status=pull_request.status,
        )
        runner_status = f"pr_{pull_request.status}"
        self.store.update_improvement_task(
            improvement_id,
            runner_status=runner_status,
            branch_name=pull_request.branch_name,
        )
        self.store.update_pull_request(
            pull_request_id,
            status=pull_request.status,
            merged_at=pull_request.merged_at,
            url=pull_request.url,
            branch_name=pull_request.branch_name,
        )
        if existing is None:
            self.store.add_audit_log(
                actor_source=actor_source,
                actor_user_id=actor_user_id,
                action="improvement.pr_open",
                target=f"pull_request:{pull_request.number}",
                risk_level="high",
                detail=pull_request.url,
            )
        if pull_request.status == "open":
            self.notifier.ensure_pr_opened(pull_request.number, pull_request.url, title)
        return PullRequestOpened(
            pull_request_id=pull_request_id,
            number=pull_request.number,
            url=pull_request.url,
            branch_name=pull_request.branch_name,
            status=pull_request.status,
        )

    def _tracked_pull_request(
        self,
        record: dict[str, object],
        title: str,
    ) -> PullRequestOpened:
        record = self._refresh_tracked_pull_request(record)
        improvement_id = int(record["improvement_task_id"])
        branch_name = str(record["branch_name"])
        status = str(record["status"])
        self.store.update_improvement_task(
            improvement_id,
            runner_status=f"pr_{status}",
            branch_name=branch_name,
        )
        if status == "open":
            self.notifier.ensure_pr_opened(
                int(record["number"]),
                str(record["url"]),
                title,
            )
        return PullRequestOpened(
            pull_request_id=int(record["id"]),
            number=int(record["number"]),
            url=str(record["url"]),
            branch_name=branch_name,
            status=status,
        )

    def _refresh_tracked_pull_request(
        self,
        record: dict[str, object],
    ) -> dict[str, object]:
        owner = str(record["github_owner"])
        repo = str(record["github_repo"])
        github = self.github
        if github.owner != owner or github.repo != repo:
            github = GitHubClient(github.settings, owner=owner, repo=repo)
        try:
            remote = github.get_pull_request(int(record["number"]))
        except Exception:
            return record
        merged = bool(remote.get("merged"))
        state = str(remote.get("state", ""))
        status = "merged" if merged else ("closed" if state == "closed" else "open")
        head = remote.get("head", {})
        branch_name = str(head.get("ref", "")) if isinstance(head, dict) else ""
        self.store.update_pull_request(
            int(record["id"]),
            status=status,
            merged_at=str(remote.get("merged_at") or ""),
            url=str(remote.get("html_url") or record["url"]),
            branch_name=branch_name or str(record["branch_name"]),
        )
        return self.store.get_pull_request(int(record["id"])) or record

    def _pull_request_result(
        self,
        remote: dict[str, object],
        branch_name: str,
    ) -> PullRequestResult:
        merged = bool(remote.get("merged"))
        state = str(remote.get("state", ""))
        status = "merged" if merged else ("closed" if state == "closed" else "open")
        return PullRequestResult(
            number=int(remote["number"]),
            url=str(remote["html_url"]),
            branch_name=branch_name,
            status=status,
            merged_at=str(remote.get("merged_at") or ""),
        )

    def _require_improvement_marker(
        self,
        remote: dict[str, object],
        improvement_id: int,
    ) -> None:
        marker = f"<!-- gugabobo-improvement:{improvement_id} -->"
        if marker not in str(remote.get("body", "")):
            raise ImprovementError(
                "remote pull request does not belong to this improvement task"
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

    def _branch_name(self, improvement_id: int, improvement: dict[str, object]) -> str:
        existing = str(improvement.get("branch_name", "")).strip()
        return existing or f"gugabobo/improvement-{improvement_id}-{uuid4().hex[:8]}"

    def _safe_error(self, error: object) -> str:
        settings = get_settings()
        return redact_sensitive(
            error,
            (
                settings.admin_token,
                settings.github_token,
                settings.telegram_bot_token,
                settings.telegram_webhook_secret,
                settings.moonshot_api_key,
                settings.deepseek_api_key,
                settings.openai_api_key,
                settings.claude_auth_token,
            ),
        )[:2000]

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
            f"<!-- gugabobo-improvement:{improvement_id} -->\n"
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
