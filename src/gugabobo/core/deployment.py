from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings
from gugabobo.infra.redaction import redact_sensitive
from gugabobo.memory.store import MemoryStore


class DeploymentError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeploymentOutcome:
    current_revision: str
    examined: int
    deployed: int
    pending: int


@dataclass(frozen=True)
class DeploymentReportOutcome:
    revision: str
    status: str
    updated: int


class DeploymentService:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()

    def record_current(
        self,
        repo: Path | None = None,
        actor_source: str = "cli",
        actor_user_id: str = "local",
    ) -> DeploymentOutcome:
        repository = (repo or Path.cwd()).resolve()
        current_revision = self._git(repository, "rev-parse", "HEAD")
        records = self.store.list_deployment_records(
            limit=500,
            status="pending",
            environment=self.settings.env,
        )
        deployed = 0
        for record in records:
            target_revision = str(record["target_revision"])
            if not self._is_ancestor(repository, target_revision, current_revision):
                continue
            self.store.mark_deployment_record(
                int(record["id"]),
                "deployed",
                deployed_revision=current_revision,
                detail=f"verified in {repository}",
            )
            deployed += 1
            self.store.add_audit_log(
                actor_source=actor_source,
                actor_user_id=actor_user_id,
                action="deployment.verified",
                target=f"deployment:{record['id']}",
                risk_level="high",
                detail=current_revision,
            )
        return DeploymentOutcome(
            current_revision=current_revision,
            examined=len(records),
            deployed=deployed,
            pending=len(records) - deployed,
        )

    def report(
        self,
        revision: str,
        status: str,
        detail: str,
        current_revision: str = "",
        actor_source: str = "deployment",
        actor_user_id: str = "server",
    ) -> DeploymentReportOutcome:
        if status not in {"deployed", "failed"}:
            raise DeploymentError("deployment status must be deployed or failed")
        records = self.store.list_deployment_records(
            limit=500,
            environment=self.settings.env,
        )
        matching = [
            record
            for record in records
            if record["target_revision"] == revision
            and record["status"] in {"pending", status}
        ]
        reported_current = current_revision or (
            revision if status == "deployed" else "unknown"
        )
        for record in matching:
            self.store.mark_deployment_record(
                int(record["id"]),
                status,
                deployed_revision=current_revision or (revision if status == "deployed" else ""),
                detail=detail,
            )
            self.store.add_audit_log(
                actor_source=actor_source,
                actor_user_id=actor_user_id,
                action=f"deployment.{status}",
                target=f"deployment:{record['id']}",
                status="success" if status == "deployed" else "failed",
                risk_level="high",
                detail=f"target={revision} current={reported_current}",
            )
        return DeploymentReportOutcome(revision, status, len(matching))

    def _git(self, repo: Path, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except OSError as error:
            raise DeploymentError(str(error)) from error
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
            raise DeploymentError(self._safe_error(detail))
        return result.stdout.strip()

    def _is_ancestor(self, repo: Path, target: str, current: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", target, current],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        detail = result.stderr.strip() or result.stdout.strip() or "git ancestry check failed"
        raise DeploymentError(self._safe_error(detail))

    def _safe_error(self, detail: object) -> str:
        return redact_sensitive(
            detail,
            (
                self.settings.github_token,
                self.settings.admin_token,
                self.settings.telegram_bot_token,
            ),
        )[:2000]
