from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from gugabobo.config import Settings, get_settings
from gugabobo.core.channel import ChannelContext
from gugabobo.core.notifications import OwnerNotifier
from gugabobo.infra.github_client import GitHubClient
from gugabobo.infra.redaction import redact_sensitive
from gugabobo.memory.store import MemoryStore


_APPROVE_PATTERNS = (
    re.compile(r"^(?:同意|批准)合并\s*(?:PR)?\s*#?(\d+)\s*$", re.IGNORECASE),
    re.compile(r"^/(?:merge|approve-merge)\s+#?(\d+)\s*$", re.IGNORECASE),
    re.compile(r"^merge\s+(?:PR\s*)?#?(\d+)\s*$", re.IGNORECASE),
)
_REJECT_PATTERNS = (
    re.compile(r"^拒绝合并\s*(?:PR)?\s*#?(\d+)\s*$", re.IGNORECASE),
    re.compile(r"^/(?:reject-merge|close-pr)\s+#?(\d+)\s*$", re.IGNORECASE),
)
_IMPLICIT_APPROVE_PATTERNS = (
    re.compile(r"^(?:同意合并|批准合并|可以合并|确认合并|合并吧)[。.!！]?$", re.IGNORECASE),
    re.compile(r"^/(?:merge|approve-merge)\s*$", re.IGNORECASE),
)
_IMPLICIT_REJECT_PATTERNS = (
    re.compile(r"^(?:拒绝合并|不要合并|不合并)[。.!！]?$", re.IGNORECASE),
    re.compile(r"^/(?:reject-merge|close-pr)\s*$", re.IGNORECASE),
)


class LifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class LifecycleOutcome:
    status: str
    pr_number: int
    checks_status: str = "unknown"
    message: str = ""


def parse_merge_command(text: str) -> tuple[str, int | None] | None:
    stripped = text.strip()
    for pattern in _APPROVE_PATTERNS:
        match = pattern.fullmatch(stripped)
        if match:
            return "approve", int(match.group(1))
    for pattern in _REJECT_PATTERNS:
        match = pattern.fullmatch(stripped)
        if match:
            return "reject", int(match.group(1))
    if any(pattern.fullmatch(stripped) for pattern in _IMPLICIT_APPROVE_PATTERNS):
        return "approve", None
    if any(pattern.fullmatch(stripped) for pattern in _IMPLICIT_REJECT_PATTERNS):
        return "reject", None
    return None


def is_merge_command(text: str) -> bool:
    return parse_merge_command(text) is not None


class PullRequestLifecycleService:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings | None = None,
        github_client: GitHubClient | None = None,
        notifier: OwnerNotifier | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self.github = github_client or GitHubClient(self.settings)
        self.notifier = notifier or OwnerNotifier(store, self.settings)

    def handle_command(self, text: str, context: ChannelContext) -> str | None:
        command = parse_merge_command(text)
        if not command:
            return None
        if not context.is_owner:
            return "只有已登记的主人可以批准或拒绝合并 PR。"
        action, pr_number = command
        if pr_number is None:
            record = self.store.get_latest_notified_open_pull_request(
                context.platform,
                context.user_id,
                self.settings.github_owner,
                self.settings.github_repo,
            )
            if not record:
                return "没有找到最近通知你的待处理 PR。"
            pr_number = int(record["number"])
        if action == "approve":
            outcome = self.approve_merge(pr_number, context, text)
        else:
            outcome = self.reject_merge(pr_number, context, text)
        return outcome.message

    def approve_merge(
        self,
        pr_number: int,
        context: ChannelContext,
        command: str = "",
    ) -> LifecycleOutcome:
        self._require_owner(context)
        record = self._record_by_number(pr_number)
        return self._approve_record(record, context, command)

    def approve_merge_record(
        self,
        pull_request_id: int,
        context: ChannelContext,
        command: str = "",
    ) -> LifecycleOutcome:
        self._require_owner(context)
        record = self.store.get_pull_request(pull_request_id)
        if not record:
            raise LifecycleError(f"pull request #{pull_request_id} not found")
        return self._approve_record(record, context, command)

    def _approve_record(
        self,
        record: dict[str, object],
        context: ChannelContext,
        command: str,
    ) -> LifecycleOutcome:
        pr_number = int(record["number"])
        pull_request_id = int(record["id"])
        if str(record["status"]) == "merged":
            return LifecycleOutcome(
                status="merged",
                pr_number=pr_number,
                checks_status=str(record["checks_status"]),
                message=f"PR #{pr_number} 已经合并。",
            )
        github = self._github_for(record)
        try:
            remote = github.get_pull_request(pr_number)
        except Exception as error:
            raise LifecycleError(self._safe_error(error)) from error
        if bool(remote.get("merged")) or str(remote.get("state", "")) == "closed":
            return self.process(pull_request_id, response_context=context)
        head = remote.get("head", {})
        head_sha = str(head.get("sha", "")) if isinstance(head, dict) else ""
        if not head_sha:
            raise LifecycleError(f"无法读取 PR #{pr_number} 的当前提交。")
        self.store.upsert_merge_authorization(
            pull_request_id=pull_request_id,
            decision="approved",
            status="approved",
            authorized_head_sha=head_sha,
            actor_platform=context.platform,
            actor_source=context.source,
            actor_user_id=context.user_id,
            command=command,
        )
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="pull_request.merge_approved",
            target=f"pull_request:{pr_number}",
            risk_level="high",
            detail=f"platform:{context.platform}; head:{head_sha}",
        )
        return self.process(pull_request_id, response_context=context)

    def reject_merge(
        self,
        pr_number: int,
        context: ChannelContext,
        command: str = "",
    ) -> LifecycleOutcome:
        self._require_owner(context)
        record = self._record_by_number(pr_number)
        return self._reject_record(record, context, command)

    def reject_merge_record(
        self,
        pull_request_id: int,
        context: ChannelContext,
        command: str = "",
    ) -> LifecycleOutcome:
        self._require_owner(context)
        record = self.store.get_pull_request(pull_request_id)
        if not record:
            raise LifecycleError(f"pull request #{pull_request_id} not found")
        return self._reject_record(record, context, command)

    def _reject_record(
        self,
        record: dict[str, object],
        context: ChannelContext,
        command: str,
    ) -> LifecycleOutcome:
        pr_number = int(record["number"])
        pull_request_id = int(record["id"])
        if str(record["status"]) == "merged":
            return LifecycleOutcome(
                status="merged",
                pr_number=pr_number,
                checks_status=str(record["checks_status"]),
                message=f"PR #{pr_number} 已经合并，不能再拒绝。",
            )
        github = self._github_for(record)
        try:
            remote = github.get_pull_request(pr_number)
            if bool(remote.get("merged")) or str(remote.get("state", "")) == "closed":
                return self.process(pull_request_id, response_context=context)
            closed = github.close_pull_request(pr_number)
            if bool(closed.get("merged")):
                return self.process(pull_request_id, response_context=context)
        except Exception as error:
            raise LifecycleError(self._safe_error(error)) from error
        self.store.update_pull_request(pull_request_id, status="closed")
        self.store.upsert_merge_authorization(
            pull_request_id=pull_request_id,
            decision="rejected",
            status="rejected",
            authorized_head_sha="",
            actor_platform=context.platform,
            actor_source=context.source,
            actor_user_id=context.user_id,
            command=command,
        )
        self._complete_rejected(record, response_context=context)
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="pull_request.merge_rejected",
            target=f"pull_request:{pr_number}",
            risk_level="high",
            detail=f"platform:{context.platform}",
        )
        return LifecycleOutcome(
            status="rejected",
            pr_number=pr_number,
            checks_status=str(record["checks_status"]),
            message=f"已拒绝并关闭 PR #{pr_number}。",
        )

    def process(
        self,
        pull_request_id: int,
        response_context: ChannelContext | None = None,
    ) -> LifecycleOutcome:
        record = self.store.get_pull_request(pull_request_id)
        if not record:
            raise LifecycleError(f"pull request #{pull_request_id} not found")
        github = self._github_for(record)
        number = int(record["number"])
        try:
            remote = github.get_pull_request(number)
            merged = bool(remote.get("merged"))
            state = str(remote.get("state", ""))
            status = "merged" if merged else ("closed" if state == "closed" else "open")
            head_sha = str(remote.get("head", {}).get("sha", ""))
        except Exception as error:
            raise LifecycleError(self._safe_error(error)) from error
        try:
            checks_status = github.get_checks_status(head_sha) if head_sha else "unknown"
        except Exception:
            checks_status = "unknown"
        merged_at = str(remote.get("merged_at") or "")
        self.store.update_pull_request(
            pull_request_id,
            status=status,
            checks_status=checks_status,
            merged_at=merged_at,
        )
        if status == "merged":
            merge_sha = str(remote.get("merge_commit_sha") or "")
            self._complete_merged(
                record,
                merge_sha,
                merged_at,
                checks_status,
                response_context=response_context,
            )
            return LifecycleOutcome(
                status="merged",
                pr_number=number,
                checks_status=checks_status,
                message=f"PR #{number} 已合并。",
            )
        if status == "closed":
            self._complete_rejected(record, response_context=response_context)
            return LifecycleOutcome(
                status="rejected",
                pr_number=number,
                checks_status=checks_status,
                message=f"PR #{number} 已关闭且未合并。",
            )
        authorization = self.store.get_merge_authorization(pull_request_id)
        if not authorization or authorization["decision"] != "approved":
            return LifecycleOutcome(
                status="open",
                pr_number=number,
                checks_status=checks_status,
                message=f"PR #{number} 仍在等待主人授权。",
            )
        if str(authorization["status"]) == "head_changed":
            return LifecycleOutcome(
                status="head_changed",
                pr_number=number,
                checks_status=checks_status,
                message=f"PR #{number} 已新增提交，需要主人重新授权。",
            )
        authorized_head_sha = str(authorization.get("authorized_head_sha", ""))
        if not authorized_head_sha or authorized_head_sha != head_sha:
            return self._mark_head_changed(
                record,
                authorization,
                authorized_head_sha,
                head_sha,
                checks_status,
            )
        claimed = self.store.claim_merge_authorization(
            pull_request_id,
            authorized_head_sha,
        )
        if claimed is None:
            return LifecycleOutcome(
                status="merge_pending",
                pr_number=number,
                checks_status=checks_status,
                message=f"PR #{number} 正在执行合并，请稍候。",
            )
        try:
            result = github.merge_pull_request(
                number,
                commit_title=f"Merge PR #{number} via gugabobo owner approval",
                sha=authorized_head_sha,
            )
        except Exception as error:
            return self._handle_merge_failure(
                record,
                github,
                claimed,
                authorized_head_sha,
                checks_status,
                error,
                response_context,
            )
        if not result.merged:
            return self._handle_merge_failure(
                record,
                github,
                claimed,
                authorized_head_sha,
                checks_status,
                result.message or "GitHub refused the merge",
                response_context,
            )
        merged_at = datetime.now(timezone.utc).isoformat()
        self.store.update_pull_request(
            pull_request_id,
            status="merged",
            checks_status=checks_status,
            merged_at=merged_at,
        )
        self._update_authorization(claimed, "merged", result.sha)
        self._complete_merged(
            record,
            result.sha,
            merged_at,
            checks_status,
            response_context=response_context,
        )
        self.store.add_audit_log(
            actor_source="github",
            actor_user_id="gugabobo",
            action="pull_request.merged",
            target=f"pull_request:{number}",
            risk_level="high",
            detail=result.sha,
        )
        return LifecycleOutcome(
            status="merged",
            pr_number=number,
            checks_status=checks_status,
            message=f"PR #{number} 已合并。",
        )

    def tick(self, limit: int = 100) -> dict[str, int]:
        if not self.github.configured:
            notification_result = self.notifier.retry_pending()
            return {
                "processed": 0,
                "merged": 0,
                "errors": 0,
                "notifications_sent": notification_result["sent"],
            }
        processed = 0
        merged = 0
        errors = 0
        for record in self.store.list_pull_requests(limit=limit):
            if str(record["status"]) != "open":
                continue
            try:
                outcome = self.process(int(record["id"]))
            except LifecycleError as error:
                errors += 1
                self.store.add_audit_log(
                    actor_source="daemon",
                    actor_user_id="gugabobo",
                    action="pull_request.sync",
                    target=f"pull_request:{record['number']}",
                    status="failed",
                    risk_level="high",
                    detail=str(error)[:1000],
                )
                continue
            processed += 1
            if outcome.status == "merged":
                merged += 1
        notification_result = self.notifier.retry_pending()
        return {
            "processed": processed,
            "merged": merged,
            "errors": errors,
            "notifications_sent": notification_result["sent"],
        }

    def _record_by_number(self, pr_number: int) -> dict[str, object]:
        record = self.store.get_pull_request_by_number(
            pr_number,
            self.settings.github_owner,
            self.settings.github_repo,
        )
        if not record:
            raise LifecycleError(f"未找到由 gugabobo 记录的 PR #{pr_number}。")
        return record

    def _github_for(self, record: dict[str, object]) -> GitHubClient:
        owner = str(record["github_owner"])
        repo = str(record["github_repo"])
        if self.github.owner == owner and self.github.repo == repo:
            return self.github
        return GitHubClient(self.settings, owner=owner, repo=repo)

    def _require_owner(self, context: ChannelContext) -> None:
        if not context.is_owner:
            raise LifecycleError("只有已登记的主人可以批准或拒绝合并 PR。")

    def _handle_merge_failure(
        self,
        record: dict[str, object],
        github: GitHubClient,
        authorization: dict[str, object],
        authorized_head_sha: str,
        checks_status: str,
        failure: object,
        response_context: ChannelContext | None,
    ) -> LifecycleOutcome:
        number = int(record["number"])
        pull_request_id = int(record["id"])
        try:
            remote = github.get_pull_request(number)
        except Exception:
            remote = {}
        if bool(remote.get("merged")):
            merge_sha = str(remote.get("merge_commit_sha") or "")
            merged_at = str(remote.get("merged_at") or datetime.now(timezone.utc).isoformat())
            self.store.update_pull_request(
                pull_request_id,
                status="merged",
                checks_status=checks_status,
                merged_at=merged_at,
            )
            self._update_authorization(authorization, "merged", merge_sha)
            self._complete_merged(
                record,
                merge_sha,
                merged_at,
                checks_status,
                response_context=response_context,
            )
            return LifecycleOutcome(
                status="merged",
                pr_number=number,
                checks_status=checks_status,
                message=f"PR #{number} 已合并。",
            )
        head = remote.get("head", {})
        current_head_sha = str(head.get("sha", "")) if isinstance(head, dict) else ""
        if current_head_sha and current_head_sha != authorized_head_sha:
            return self._mark_head_changed(
                record,
                authorization,
                authorized_head_sha,
                current_head_sha,
                checks_status,
            )
        detail = self._safe_error(failure)
        self._update_authorization(authorization, "merge_pending", detail)
        self._record_blocked(record, "merge_failed", detail)
        return LifecycleOutcome(
            status="merge_pending",
            pr_number=number,
            checks_status=checks_status,
            message=f"PR #{number} 暂未合并，后台会自动重试。",
        )

    def _mark_head_changed(
        self,
        record: dict[str, object],
        authorization: dict[str, object],
        authorized_head_sha: str,
        current_head_sha: str,
        checks_status: str,
    ) -> LifecycleOutcome:
        number = int(record["number"])
        previous = authorized_head_sha or "missing"
        current = current_head_sha or "missing"
        detail = f"authorized head {previous} changed to {current}"
        already_recorded = (
            str(authorization["status"]) == "head_changed"
            and str(authorization["detail"]) == detail
        )
        self._update_authorization(authorization, "head_changed", detail)
        if not already_recorded:
            self._record_blocked(record, "head_changed", detail)
            self.store.add_audit_log(
                actor_source="github",
                actor_user_id="gugabobo",
                action="pull_request.head_changed",
                target=f"pull_request:{number}",
                status="blocked",
                risk_level="high",
                detail=detail,
            )
            self.notifier.notify_pr_head_changed(
                number,
                str(record["url"]),
                authorized_head_sha,
                current_head_sha,
            )
        return LifecycleOutcome(
            status="head_changed",
            pr_number=number,
            checks_status=checks_status,
            message=f"PR #{number} 已新增提交，需要主人重新授权。",
        )

    def _update_authorization(
        self,
        authorization: dict[str, object],
        status: str,
        detail: str,
    ) -> None:
        self.store.upsert_merge_authorization(
            pull_request_id=int(authorization["pull_request_id"]),
            decision=str(authorization["decision"]),
            status=status,
            authorized_head_sha=str(authorization.get("authorized_head_sha", "")),
            actor_platform=str(authorization["actor_platform"]),
            actor_source=str(authorization["actor_source"]),
            actor_user_id=str(authorization["actor_user_id"]),
            command=str(authorization["command"]),
            detail=detail,
        )

    def _complete_merged(
        self,
        record: dict[str, object],
        merge_sha: str,
        merged_at: str,
        checks_status: str,
        response_context: ChannelContext | None = None,
    ) -> None:
        pull_request_id = int(record["id"])
        number = int(record["number"])
        authorization = self.store.get_merge_authorization(pull_request_id)
        if authorization and authorization["decision"] == "approved":
            self._update_authorization(authorization, "merged", merge_sha)
            actor = f"{authorization['actor_platform']}:{authorization['actor_user_id']}"
        else:
            actor = "external"
        self.store.upsert_improvement_reflection(
            improvement_task_id=int(record["improvement_task_id"]),
            pull_request_id=pull_request_id,
            outcome="merged",
            summary=f"PR #{number} merged at {merged_at or 'an unknown time'}.",
            lessons=(
                f"Outcome accepted after authorization by {actor}; checks={checks_status}. "
                "Preserve the successful scope and verification path for future improvements."
            ),
        )
        if merge_sha:
            self.store.add_deployment_record(
                pull_request_id=pull_request_id,
                environment=self.settings.env,
                target_revision=merge_sha,
                detail=f"PR #{number} merged and awaits deployment verification",
            )
        self.notifier.notify_pr_outcome(
            number,
            "merged",
            str(record["url"]),
            skip_recipient=self._notification_recipient(response_context),
        )

    def _complete_rejected(
        self,
        record: dict[str, object],
        response_context: ChannelContext | None = None,
    ) -> None:
        pull_request_id = int(record["id"])
        number = int(record["number"])
        authorization = self.store.get_merge_authorization(pull_request_id)
        if authorization and authorization["decision"] == "rejected":
            actor = f"{authorization['actor_platform']}:{authorization['actor_user_id']}"
            decision_detail = f"Rejected by {actor}."
        else:
            decision_detail = "Closed externally without a recorded owner rejection."
        self.store.upsert_improvement_reflection(
            improvement_task_id=int(record["improvement_task_id"]),
            pull_request_id=pull_request_id,
            outcome="rejected",
            summary=f"PR #{number} was closed without merge.",
            lessons=(
                f"{decision_detail} Review the PR discussion, scope, "
                "and verification evidence before proposing a replacement."
            ),
        )
        self.notifier.notify_pr_outcome(
            number,
            "rejected",
            str(record["url"]),
            skip_recipient=self._notification_recipient(response_context),
        )

    def _notification_recipient(
        self,
        context: ChannelContext | None,
    ) -> tuple[str, str] | None:
        if context and context.platform in {"qq", "telegram"}:
            return context.platform, context.user_id
        return None

    def _record_blocked(
        self,
        record: dict[str, object],
        outcome: str,
        reason: str,
    ) -> None:
        number = int(record["number"])
        self.store.upsert_improvement_reflection(
            improvement_task_id=int(record["improvement_task_id"]),
            pull_request_id=int(record["id"]),
            outcome=outcome,
            summary=f"PR #{number} automatic merge was blocked.",
            lessons=f"Failure reason: {reason}",
        )

    def _safe_error(self, error: object) -> str:
        return redact_sensitive(
            error,
            (
                self.settings.github_token,
                self.settings.admin_token,
                self.settings.telegram_bot_token,
                self.settings.napcat_access_token,
            ),
        )[:2000]
