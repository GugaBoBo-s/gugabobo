from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    conversation_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    updated_until_message_id INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 5,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',
    merged_into_person_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channel_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_user_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_accounts_person_id
ON channel_accounts(person_id);

CREATE TABLE IF NOT EXISTS account_link_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    source_platform TEXT NOT NULL,
    source_user_id TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TEXT NOT NULL DEFAULT (datetime('now', '+10 minutes')),
    consumed_by_platform TEXT NOT NULL DEFAULT '',
    consumed_by_user_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consumed_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_account_link_codes_status_expires
ON account_link_codes(status, expires_at);

CREATE TABLE IF NOT EXISTS access_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    display_name TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, user_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_source TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'normal',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    created_by TEXT NOT NULL DEFAULT '',
    assigned_skill TEXT NOT NULL DEFAULT '',
    requires_approval INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS improvement_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL DEFAULT 0,
    feedback_id INTEGER NOT NULL DEFAULT 0,
    repo TEXT NOT NULL DEFAULT '',
    branch_name TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'normal',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    runner_status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    improvement_task_id INTEGER NOT NULL DEFAULT 0,
    github_owner TEXT NOT NULL DEFAULT '',
    github_repo TEXT NOT NULL DEFAULT '',
    number INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL DEFAULT '',
    branch_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    checks_status TEXT NOT NULL DEFAULT 'unknown',
    merged_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS code_review_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_owner TEXT NOT NULL,
    github_repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_url TEXT NOT NULL DEFAULT '',
    head_sha TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    attempt_count INTEGER NOT NULL DEFAULT 1,
    review_id INTEGER NOT NULL DEFAULT 0,
    review_url TEXT NOT NULL DEFAULT '',
    findings_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT NOT NULL DEFAULT '',
    UNIQUE(github_owner, github_repo, pr_number, head_sha)
);

CREATE INDEX IF NOT EXISTS idx_code_review_runs_status_updated
ON code_review_runs(status, updated_at);

CREATE TABLE IF NOT EXISTS github_issue_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_owner TEXT NOT NULL,
    github_repo TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    issue_url TEXT NOT NULL DEFAULT '',
    issue_updated_at TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'processing',
    attempt_count INTEGER NOT NULL DEFAULT 1,
    worthwhile INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    rationale TEXT NOT NULL DEFAULT '',
    implementation_summary TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    improvement_task_id INTEGER NOT NULL DEFAULT 0,
    pr_number INTEGER NOT NULL DEFAULT 0,
    pr_url TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT NOT NULL DEFAULT '',
    UNIQUE(github_owner, github_repo, issue_number, issue_updated_at)
);

CREATE INDEX IF NOT EXISTS idx_github_issue_runs_status_updated
ON github_issue_runs(status, updated_at);

CREATE TABLE IF NOT EXISTS execution_runs (
    run_type TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    lease_token TEXT NOT NULL DEFAULT '',
    worker_id TEXT NOT NULL DEFAULT '',
    container_name TEXT NOT NULL DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_expires_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancel_requested_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(run_type, run_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_runs_status_lease
ON execution_runs(status, lease_expires_at);

CREATE TABLE IF NOT EXISTS merge_authorizations (
    pull_request_id INTEGER PRIMARY KEY,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    authorized_head_sha TEXT NOT NULL DEFAULT '',
    actor_platform TEXT NOT NULL,
    actor_source TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    command TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS improvement_reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    improvement_task_id INTEGER NOT NULL,
    pull_request_id INTEGER NOT NULL UNIQUE,
    outcome TEXT NOT NULL,
    summary TEXT NOT NULL,
    lessons TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deployment_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pull_request_id INTEGER NOT NULL,
    environment TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    deployed_revision TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deployed_at TEXT NOT NULL DEFAULT '',
    UNIQUE(pull_request_id, environment, target_revision)
);

CREATE TABLE IF NOT EXISTS owner_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    platform TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(dedupe_key, platform, recipient_id)
);

CREATE TABLE IF NOT EXISTS outbound_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    actor_source TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    target TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    recipient_label TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TEXT NOT NULL DEFAULT (datetime('now', '+10 minutes')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inbound_events (
    platform TEXT NOT NULL,
    event_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    reply TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(platform, event_id)
);

CREATE TABLE IF NOT EXISTS automation_cursors (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class MemoryStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_access_rules(conn)
            self._migrate_audit_logs(conn)
            self._migrate_github_lifecycle(conn)
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "conversation_id" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "UPDATE messages SET conversation_id = source || ':' || user_id "
                "WHERE conversation_id = '' AND role = 'user'"
            )
            conn.execute(
                "UPDATE messages SET conversation_id = source || ':local' "
                "WHERE conversation_id = '' AND role = 'assistant'"
            )
            assistant_rows = conn.execute(
                "SELECT id, source FROM messages "
                "WHERE role = 'assistant' AND conversation_id = source || ':local'"
            ).fetchall()
            for row in assistant_rows:
                previous_user = conn.execute(
                    "SELECT conversation_id FROM messages "
                    "WHERE role = 'user' AND source = ? AND id < ? "
                    "ORDER BY id DESC LIMIT 1",
                    (row["source"], row["id"]),
                ).fetchone()
                if previous_user:
                    conn.execute(
                        "UPDATE messages SET conversation_id = ? WHERE id = ?",
                        (previous_user["conversation_id"], row["id"]),
                    )

    def _migrate_access_rules(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(access_rules)").fetchall()
        }
        expected = {
            "display_name": "TEXT NOT NULL DEFAULT ''",
            "notes": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        }
        for column, definition in expected.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE access_rules ADD COLUMN {column} {definition}")

    def _migrate_audit_logs(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()
        }
        if "risk_level" not in columns:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'normal'")

    def _migrate_github_lifecycle(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(merge_authorizations)").fetchall()
        }
        if "authorized_head_sha" not in columns:
            conn.execute(
                "ALTER TABLE merge_authorizations ADD COLUMN "
                "authorized_head_sha TEXT NOT NULL DEFAULT ''"
            )
        notifications = conn.execute(
            "SELECT id, dedupe_key, platform, recipient_id FROM owner_notifications "
            "WHERE dedupe_key LIKE 'pr:%'"
        ).fetchall()
        for notification in notifications:
            parts = str(notification["dedupe_key"]).split(":")
            if len(parts) < 3 or not parts[1].isdigit():
                continue
            repositories = conn.execute(
                "SELECT github_owner, github_repo FROM pull_requests WHERE number = ? "
                "GROUP BY github_owner, github_repo",
                (int(parts[1]),),
            ).fetchall()
            if len(repositories) != 1:
                continue
            owner = str(repositories[0]["github_owner"]).casefold()
            repo = str(repositories[0]["github_repo"]).casefold()
            new_key = f"pr:{owner}/{repo}:{parts[1]}:{':'.join(parts[2:])}"
            duplicate = conn.execute(
                "SELECT id FROM owner_notifications WHERE dedupe_key = ? AND platform = ? "
                "AND recipient_id = ? AND id != ?",
                (
                    new_key,
                    notification["platform"],
                    notification["recipient_id"],
                    notification["id"],
                ),
            ).fetchone()
            if duplicate:
                conn.execute(
                    "DELETE FROM owner_notifications WHERE id = ?",
                    (notification["id"],),
                )
            else:
                conn.execute(
                    "UPDATE owner_notifications SET dedupe_key = ? WHERE id = ?",
                    (new_key, notification["id"]),
                )

    def ensure_channel_account(
        self,
        platform: str,
        platform_user_id: str,
        role: str = "user",
    ) -> dict[str, Any]:
        normalized_role = role if role in {"owner", "trusted"} else "user"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._get_channel_account(conn, platform, platform_user_id)
            if row:
                current_role = str(row["person_role"])
                promoted_role = self._higher_role(current_role, normalized_role)
                if promoted_role != current_role:
                    conn.execute(
                        "UPDATE persons SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (promoted_role, row["person_id"]),
                    )
                return dict(self._get_channel_account(conn, platform, platform_user_id))
            person_cursor = conn.execute("INSERT INTO persons (role) VALUES (?)", (normalized_role,))
            person_id = int(person_cursor.lastrowid)
            conn.execute(
                "INSERT INTO channel_accounts (person_id, platform, platform_user_id) "
                "VALUES (?, ?, ?)",
                (person_id, platform, platform_user_id),
            )
            return dict(self._get_channel_account(conn, platform, platform_user_id))

    def get_channel_account(
        self,
        platform: str,
        platform_user_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = self._get_channel_account(conn, platform, platform_user_id)
        return dict(row) if row else None

    def resolve_conversation_id(self, conversation_id: str) -> str:
        prefixes = {
            "qq:user:": "qq",
            "telegram:user:": "telegram",
        }
        for prefix, platform in prefixes.items():
            if not conversation_id.startswith(prefix):
                continue
            platform_user_id = conversation_id[len(prefix) :]
            account = self.get_channel_account(platform, platform_user_id)
            if account:
                return f"person:{account['person_id']}:direct"
        return conversation_id

    def list_person_accounts(self, person_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, person_id, platform, platform_user_id, verified_at, "
                "created_at, updated_at FROM channel_accounts "
                "WHERE person_id = ? ORDER BY id ASC",
                (person_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def migrate_private_conversation(
        self,
        legacy_conversation_id: str,
        canonical_conversation_id: str,
    ) -> None:
        if legacy_conversation_id == canonical_conversation_id:
            return
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE messages SET conversation_id = ? WHERE conversation_id = ?",
                (canonical_conversation_id, legacy_conversation_id),
            )
            conn.execute(
                "UPDATE memory_items SET subject = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE subject = ?",
                (canonical_conversation_id, legacy_conversation_id),
            )
            conn.execute(
                "UPDATE outbound_drafts SET conversation_id = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE conversation_id = ?",
                (canonical_conversation_id, legacy_conversation_id),
            )
            legacy_summary = conn.execute(
                "SELECT summary FROM conversation_summaries WHERE conversation_id = ?",
                (legacy_conversation_id,),
            ).fetchone()
            canonical_summary = conn.execute(
                "SELECT summary FROM conversation_summaries WHERE conversation_id = ?",
                (canonical_conversation_id,),
            ).fetchone()
            if legacy_summary and not canonical_summary:
                conn.execute(
                    "UPDATE conversation_summaries SET conversation_id = ? "
                    "WHERE conversation_id = ?",
                    (canonical_conversation_id, legacy_conversation_id),
                )
            elif legacy_summary:
                conn.execute(
                    "INSERT INTO memory_items "
                    "(subject, memory_type, content, importance, source) "
                    "VALUES (?, 'linked_summary', ?, 7, 'identity_migration')",
                    (canonical_conversation_id, legacy_summary["summary"]),
                )
                conn.execute(
                    "DELETE FROM conversation_summaries WHERE conversation_id = ?",
                    (legacy_conversation_id,),
                )
                conn.execute(
                    "UPDATE conversation_summaries SET updated_until_message_id = 0, "
                    "updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
                    (canonical_conversation_id,),
                )

    def create_account_link_code(
        self,
        person_id: int,
        source_platform: str,
        source_user_id: str,
        code_hash: str,
        expires_in_minutes: int = 10,
    ) -> int:
        modifier = f"+{max(1, expires_in_minutes)} minutes"
        with self.connect() as conn:
            conn.execute(
                "UPDATE account_link_codes SET status = 'revoked' "
                "WHERE source_platform = ? AND source_user_id = ? AND status = 'pending'",
                (source_platform, source_user_id),
            )
            cursor = conn.execute(
                "INSERT INTO account_link_codes "
                "(person_id, source_platform, source_user_id, code_hash, expires_at) "
                "VALUES (?, ?, ?, ?, datetime('now', ?))",
                (person_id, source_platform, source_user_id, code_hash, modifier),
            )
            return int(cursor.lastrowid)

    def consume_account_link_code(
        self,
        code_hash: str,
        target_platform: str,
        target_user_id: str,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            link_code = conn.execute(
                "SELECT id, person_id, source_platform, source_user_id, status, expires_at "
                "FROM account_link_codes WHERE code_hash = ?",
                (code_hash,),
            ).fetchone()
            if not link_code or link_code["status"] != "pending":
                return {"status": "invalid"}
            active = conn.execute(
                "SELECT expires_at > CURRENT_TIMESTAMP AS active "
                "FROM account_link_codes WHERE id = ?",
                (link_code["id"],),
            ).fetchone()
            if not active or not bool(active["active"]):
                conn.execute(
                    "UPDATE account_link_codes SET status = 'expired' WHERE id = ?",
                    (link_code["id"],),
                )
                return {"status": "expired"}
            if (
                link_code["source_platform"] == target_platform
                and link_code["source_user_id"] == target_user_id
            ):
                return {"status": "same_account"}
            if link_code["source_platform"] == target_platform:
                return {"status": "same_platform"}
            target_account = self._get_channel_account(conn, target_platform, target_user_id)
            if not target_account:
                return {"status": "target_missing"}
            source_person_id = int(link_code["person_id"])
            target_person_id = int(target_account["person_id"])
            if source_person_id == target_person_id:
                self._mark_link_code_consumed(
                    conn,
                    int(link_code["id"]),
                    target_platform,
                    target_user_id,
                )
                return {"status": "already_linked", "person_id": source_person_id}
            source_person = conn.execute(
                "SELECT id, role, merged_into_person_id FROM persons WHERE id = ?",
                (source_person_id,),
            ).fetchone()
            target_person = conn.execute(
                "SELECT id, role, merged_into_person_id FROM persons WHERE id = ?",
                (target_person_id,),
            ).fetchone()
            if (
                not source_person
                or not target_person
                or source_person["merged_into_person_id"] is not None
                or target_person["merged_into_person_id"] is not None
            ):
                return {"status": "stale_identity"}
            source_conversation_id = f"person:{source_person_id}:direct"
            target_conversation_id = f"person:{target_person_id}:direct"
            self._merge_private_conversations(
                conn,
                source_conversation_id,
                target_conversation_id,
            )
            merged_role = self._higher_role(
                str(source_person["role"]),
                str(target_person["role"]),
            )
            conn.execute(
                "UPDATE persons SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (merged_role, source_person_id),
            )
            conn.execute(
                "UPDATE channel_accounts SET person_id = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE person_id = ?",
                (source_person_id, target_person_id),
            )
            conn.execute(
                "UPDATE persons SET merged_into_person_id = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (source_person_id, target_person_id),
            )
            conn.execute(
                "UPDATE account_link_codes SET status = 'revoked' "
                "WHERE person_id = ? AND status = 'pending' AND id != ?",
                (target_person_id, link_code["id"]),
            )
            self._mark_link_code_consumed(
                conn,
                int(link_code["id"]),
                target_platform,
                target_user_id,
            )
            return {
                "status": "linked",
                "person_id": source_person_id,
                "merged_person_id": target_person_id,
            }

    def _get_channel_account(
        self,
        conn: sqlite3.Connection,
        platform: str,
        platform_user_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT channel_accounts.id, channel_accounts.person_id, "
            "channel_accounts.platform, channel_accounts.platform_user_id, "
            "channel_accounts.verified_at, persons.role AS person_role, "
            "persons.display_name AS person_display_name "
            "FROM channel_accounts JOIN persons ON persons.id = channel_accounts.person_id "
            "WHERE channel_accounts.platform = ? AND channel_accounts.platform_user_id = ? "
            "AND persons.merged_into_person_id IS NULL",
            (platform, platform_user_id),
        ).fetchone()

    def _merge_private_conversations(
        self,
        conn: sqlite3.Connection,
        target_conversation_id: str,
        merged_conversation_id: str,
    ) -> None:
        summaries = conn.execute(
            "SELECT conversation_id, summary FROM conversation_summaries "
            "WHERE conversation_id IN (?, ?)",
            (target_conversation_id, merged_conversation_id),
        ).fetchall()
        conn.execute(
            "UPDATE messages SET conversation_id = ? WHERE conversation_id = ?",
            (target_conversation_id, merged_conversation_id),
        )
        conn.execute(
            "UPDATE memory_items SET subject = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE subject = ?",
            (target_conversation_id, merged_conversation_id),
        )
        conn.execute(
            "UPDATE outbound_drafts SET conversation_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE conversation_id = ?",
            (target_conversation_id, merged_conversation_id),
        )
        for summary in summaries:
            conn.execute(
                "INSERT INTO memory_items "
                "(subject, memory_type, content, importance, source) "
                "VALUES (?, 'linked_summary', ?, 7, 'account_link')",
                (target_conversation_id, summary["summary"]),
            )
        conn.execute(
            "DELETE FROM conversation_summaries WHERE conversation_id IN (?, ?)",
            (target_conversation_id, merged_conversation_id),
        )

    def _merge_person_into(
        self,
        conn: sqlite3.Connection,
        keep_person_id: int,
        drop_person_id: int,
    ) -> None:
        # Fold drop_person_id into keep_person_id: move its private conversation,
        # reassign its channel accounts, and tombstone the dropped person.
        if keep_person_id == drop_person_id:
            return
        self._merge_private_conversations(
            conn,
            f"person:{keep_person_id}:direct",
            f"person:{drop_person_id}:direct",
        )
        keep = conn.execute(
            "SELECT role FROM persons WHERE id = ?", (keep_person_id,)
        ).fetchone()
        drop = conn.execute(
            "SELECT role FROM persons WHERE id = ?", (drop_person_id,)
        ).fetchone()
        merged_role = self._higher_role(
            str(keep["role"]) if keep else "user",
            str(drop["role"]) if drop else "user",
        )
        conn.execute(
            "UPDATE persons SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (merged_role, keep_person_id),
        )
        conn.execute(
            "UPDATE channel_accounts SET person_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE person_id = ?",
            (keep_person_id, drop_person_id),
        )
        conn.execute(
            "UPDATE persons SET merged_into_person_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (keep_person_id, drop_person_id),
        )

    def collapse_owner_persons(self) -> int:
        """Merge all owner-role persons into the lowest owner person id.

        Owner accounts are declared trusted-by-configuration (OWNER_*_IDS), so
        they represent the same real person and should share one identity /
        memory / context without a manual link step. Returns the surviving
        owner person id, or 0 if there are no owner persons.
        """
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id FROM persons "
                "WHERE role = 'owner' AND merged_into_person_id IS NULL "
                "ORDER BY id ASC"
            ).fetchall()
            person_ids = [int(r["id"]) for r in rows]
            if len(person_ids) <= 1:
                return person_ids[0] if person_ids else 0
            keep_id = person_ids[0]
            for drop_id in person_ids[1:]:
                self._merge_person_into(conn, keep_id, drop_id)
            return keep_id

    def _mark_link_code_consumed(
        self,
        conn: sqlite3.Connection,
        link_code_id: int,
        platform: str,
        user_id: str,
    ) -> None:
        conn.execute(
            "UPDATE account_link_codes SET status = 'consumed', "
            "consumed_by_platform = ?, consumed_by_user_id = ?, "
            "consumed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (platform, user_id, link_code_id),
        )

    @staticmethod
    def _higher_role(first: str, second: str) -> str:
        ranks = {"user": 0, "trusted": 1, "owner": 2}
        return first if ranks.get(first, 0) >= ranks.get(second, 0) else second

    def add_message(
        self,
        source: str,
        user_id: str,
        role: str,
        content: str,
        conversation_id: str,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (conversation_id, source, user_id, role, content) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, source, user_id, role, content),
            )
            return int(cursor.lastrowid)

    def list_messages(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, source, user_id, role, content, created_at "
                "FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_messages_by_source_prefix(
        self,
        source_prefix: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, source, user_id, role, content, created_at "
                "FROM messages WHERE source LIKE ? ORDER BY id DESC LIMIT ?",
                (f"{source_prefix}%", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT conversation_id, COUNT(*) AS message_count, "
                "MAX(created_at) AS last_message_at "
                "FROM messages GROUP BY conversation_id "
                "ORDER BY last_message_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, source, user_id, role, content, created_at "
                "FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def list_messages_after(
        self,
        conversation_id: str,
        after_message_id: int = 0,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            query = (
                "SELECT id, conversation_id, source, user_id, role, content, created_at "
                "FROM messages WHERE conversation_id = ? AND id > ? ORDER BY id ASC"
            )
            params: list[Any] = [conversation_id, after_message_id]
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def list_recent_messages_after(
        self,
        conversation_id: str,
        after_message_id: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        conversation_id = self.resolve_conversation_id(conversation_id)
        if limit <= 0:
            return self.list_messages_after(conversation_id, after_message_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, source, user_id, role, content, created_at FROM ("
                "SELECT id, conversation_id, source, user_id, role, content, created_at "
                "FROM messages WHERE conversation_id = ? AND id > ? "
                "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (conversation_id, after_message_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_messages_after(self, conversation_id: str, after_message_id: int = 0) -> int:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ? AND id > ?",
                (conversation_id, after_message_id),
            ).fetchone()
        return int(row["c"]) if row else 0

    def delete_conversation_messages(self, conversation_id: str) -> int:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            return cursor.rowcount

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, conversation_id, source, user_id, role, content, created_at "
                "FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_conversation_summary(
        self,
        conversation_id: str,
        summary: str,
        updated_until_message_id: int = 0,
    ) -> None:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO conversation_summaries "
                "(conversation_id, summary, updated_until_message_id, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(conversation_id) DO UPDATE SET "
                "summary = excluded.summary, "
                "updated_until_message_id = excluded.updated_until_message_id, "
                "updated_at = CURRENT_TIMESTAMP",
                (conversation_id, summary, updated_until_message_id),
            )

    def get_conversation_summary(self, conversation_id: str) -> dict[str, Any] | None:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT conversation_id, summary, updated_until_message_id, updated_at "
                "FROM conversation_summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_conversation_summaries(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT conversation_id, summary, updated_until_message_id, updated_at "
                "FROM conversation_summaries ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation_summary(self, conversation_id: str) -> bool:
        conversation_id = self.resolve_conversation_id(conversation_id)
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM conversation_summaries WHERE conversation_id = ?",
                (conversation_id,),
            )
            return cursor.rowcount > 0

    def add_memory_item(
        self,
        subject: str,
        content: str,
        memory_type: str = "note",
        importance: int = 5,
        source: str = "manual",
    ) -> int:
        subject = self.resolve_conversation_id(subject)
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO memory_items (subject, memory_type, content, importance, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (subject, memory_type, content, importance, source),
            )
            return int(cursor.lastrowid)

    def list_memory_items(
        self,
        subject: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if subject:
            subject = self.resolve_conversation_id(subject)
        with self.connect() as conn:
            if subject:
                rows = conn.execute(
                    "SELECT id, subject, memory_type, content, importance, source, "
                    "created_at, updated_at FROM memory_items "
                    "WHERE subject IN (?, 'global') "
                    "ORDER BY importance DESC, id DESC LIMIT ?",
                    (subject, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, subject, memory_type, content, importance, source, "
                    "created_at, updated_at FROM memory_items "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_memory_item(self, memory_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, subject, memory_type, content, importance, source, "
                "created_at, updated_at FROM memory_items WHERE id = ?",
                (memory_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_memory_item(
        self,
        memory_id: int,
        subject: str,
        content: str,
        memory_type: str,
        importance: int,
    ) -> bool:
        subject = self.resolve_conversation_id(subject)
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE memory_items SET subject = ?, content = ?, memory_type = ?, "
                "importance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (subject, content, memory_type, importance, memory_id),
            )
            return cursor.rowcount > 0

    def delete_memory_item(self, memory_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0

    def upsert_access_rule(
        self,
        platform: str,
        user_id: str,
        role: str,
        display_name: str = "",
        notes: str = "",
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO access_rules (platform, user_id, role, display_name, notes) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, user_id) DO UPDATE SET "
                "role = excluded.role, "
                "display_name = excluded.display_name, "
                "notes = excluded.notes, "
                "updated_at = CURRENT_TIMESTAMP",
                (platform, user_id, role, display_name, notes),
            )
            row = conn.execute(
                "SELECT id FROM access_rules WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            return int(row["id"])

    def get_access_rule(self, platform: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, platform, user_id, role, display_name, notes, created_at, updated_at "
                "FROM access_rules WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_access_rules(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, platform, user_id, role, display_name, notes, created_at, updated_at "
                "FROM access_rules ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_access_rule(self, rule_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM access_rules WHERE id = ?", (rule_id,))
            return cursor.rowcount > 0

    def add_audit_log(
        self,
        actor_source: str,
        actor_user_id: str,
        action: str,
        target: str = "",
        status: str = "ok",
        risk_level: str = "normal",
        detail: str = "",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO audit_logs "
                "(actor_source, actor_user_id, action, target, status, risk_level, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (actor_source, actor_user_id, action, target, status, risk_level, detail),
            )
            return int(cursor.lastrowid)

    def list_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, actor_source, actor_user_id, action, target, status, risk_level, detail, "
                "created_at FROM audit_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_task(
        self,
        title: str,
        description: str = "",
        status: str = "open",
        priority: str = "normal",
        created_by: str = "",
        assigned_skill: str = "",
        requires_approval: bool = True,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks "
                "(title, description, status, priority, created_by, assigned_skill, "
                "requires_approval) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    title,
                    description,
                    status,
                    priority,
                    created_by,
                    assigned_skill,
                    int(requires_approval),
                ),
            )
            return int(cursor.lastrowid)

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, title, description, status, priority, created_by, "
                "assigned_skill, requires_approval, created_at, updated_at "
                "FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, title, description, status, priority, created_by, "
                "assigned_skill, requires_approval, created_at, updated_at "
                "FROM tasks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_task_status(self, task_id: int, status: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, task_id),
            )
            return cursor.rowcount > 0

    def _recover_stale_executions(
        self,
        conn: sqlite3.Connection,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT run_type, run_id, status, container_name FROM execution_runs WHERE "
            "status IN ('running', 'cancel_requested') AND "
            "lease_expires_at <= CURRENT_TIMESTAMP"
        ).fetchall()
        for row in rows:
            status = "cancelled" if row["status"] == "cancel_requested" else "stale"
            conn.execute(
                "UPDATE execution_runs SET status = ?, lease_token = '', worker_id = '', "
                "completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE "
                "run_type = ? AND run_id = ?",
                (status, row["run_type"], row["run_id"]),
            )
            self._set_domain_execution_status(
                conn,
                str(row["run_type"]),
                int(row["run_id"]),
                status,
            )
        return [dict(row) for row in rows]

    def recover_stale_executions(self) -> int:
        return len(self.recover_stale_execution_records())

    def recover_stale_execution_records(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self._recover_stale_executions(conn)

    def _set_domain_execution_status(
        self,
        conn: sqlite3.Connection,
        run_type: str,
        run_id: int,
        status: str,
    ) -> None:
        targets = {
            "code_review": ("code_review_runs", "status"),
            "github_issue": ("github_issue_runs", "status"),
            "improvement": ("improvement_tasks", "runner_status"),
        }
        target = targets.get(run_type)
        if target is None:
            return
        table, column = target
        conn.execute(
            f"UPDATE {table} SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, run_id),
        )

    def _claim_execution(
        self,
        conn: sqlite3.Connection,
        run_type: str,
        run_id: int,
        worker_id: str,
        lease_seconds: int,
        allow_completed: bool = False,
    ) -> dict[str, Any] | None:
        self._recover_stale_executions(conn)
        row = conn.execute(
            "SELECT * FROM execution_runs WHERE run_type = ? AND run_id = ?",
            (run_type, run_id),
        ).fetchone()
        token = secrets.token_hex(16)
        container_name = f"gugabobo-{run_type.replace('_', '-')}-{run_id}-{token[:8]}"
        lease_modifier = f"+{lease_seconds} seconds"
        if row is None:
            conn.execute(
                "INSERT INTO execution_runs "
                "(run_type, run_id, lease_token, worker_id, container_name, lease_expires_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now', ?))",
                (run_type, run_id, token, worker_id, container_name, lease_modifier),
            )
        else:
            status = str(row["status"])
            claimable = {"failed", "retry_requested", "stale"}
            if allow_completed:
                claimable.add("completed")
            if status not in claimable:
                return None
            conn.execute(
                "UPDATE execution_runs SET status = 'running', lease_token = ?, worker_id = ?, "
                "container_name = ?, attempt_count = attempt_count + 1, "
                "started_at = CURRENT_TIMESTAMP, heartbeat_at = CURRENT_TIMESTAMP, "
                "lease_expires_at = datetime('now', ?), cancel_requested_at = '', "
                "completed_at = '', last_error = '', updated_at = CURRENT_TIMESTAMP "
                "WHERE run_type = ? AND run_id = ?",
                (token, worker_id, container_name, lease_modifier, run_type, run_id),
            )
        claimed = conn.execute(
            "SELECT * FROM execution_runs WHERE run_type = ? AND run_id = ?",
            (run_type, run_id),
        ).fetchone()
        return dict(claimed) if claimed else None

    def claim_improvement_run(
        self,
        improvement_id: int,
        worker_id: str,
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            improvement = conn.execute(
                "SELECT id FROM improvement_tasks WHERE id = ?",
                (improvement_id,),
            ).fetchone()
            if improvement is None:
                return None
            claimed = self._claim_execution(
                conn,
                "improvement",
                improvement_id,
                worker_id,
                lease_seconds,
                allow_completed=True,
            )
            if claimed is None:
                return None
            conn.execute(
                "UPDATE improvement_tasks SET runner_status = 'running', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (improvement_id,),
            )
            return claimed

    def heartbeat_execution(
        self,
        run_type: str,
        run_id: int,
        lease_token: str,
        lease_seconds: int,
    ) -> bool:
        lease_modifier = f"+{lease_seconds} seconds"
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE execution_runs SET heartbeat_at = CURRENT_TIMESTAMP, "
                "lease_expires_at = datetime('now', ?), updated_at = CURRENT_TIMESTAMP "
                "WHERE run_type = ? AND run_id = ? AND lease_token = ? AND status = 'running' "
                "AND lease_expires_at > CURRENT_TIMESTAMP",
                (lease_modifier, run_type, run_id, lease_token),
            )
            return cursor.rowcount > 0

    def get_execution_run(self, run_type: str, run_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_runs WHERE run_type = ? AND run_id = ?",
                (run_type, run_id),
            ).fetchone()
        return dict(row) if row else None

    def list_execution_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT run_type, run_id, status, worker_id, container_name, attempt_count, "
                "started_at, heartbeat_at, lease_expires_at, cancel_requested_at, completed_at, "
                "last_error, created_at, updated_at FROM execution_runs "
                "ORDER BY updated_at DESC, run_type, run_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def request_execution_cancel(self, run_type: str, run_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._recover_stale_executions(conn)
            cursor = conn.execute(
                "UPDATE execution_runs SET status = 'cancel_requested', "
                "cancel_requested_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                "WHERE run_type = ? AND run_id = ? AND status = 'running'",
                (run_type, run_id),
            )
            if cursor.rowcount == 0:
                return None
            self._set_domain_execution_status(conn, run_type, run_id, "cancel_requested")
            row = conn.execute(
                "SELECT * FROM execution_runs WHERE run_type = ? AND run_id = ?",
                (run_type, run_id),
            ).fetchone()
            return dict(row) if row else None

    def request_execution_retry(self, run_type: str, run_id: int) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._recover_stale_executions(conn)
            cursor = conn.execute(
                "UPDATE execution_runs SET status = 'retry_requested', lease_token = '', "
                "worker_id = '', container_name = '', cancel_requested_at = '', "
                "completed_at = '', last_error = '', updated_at = CURRENT_TIMESTAMP "
                "WHERE run_type = ? AND run_id = ? AND status IN ('failed', 'cancelled', 'stale')",
                (run_type, run_id),
            )
            if cursor.rowcount == 0:
                return False
            self._set_domain_execution_status(conn, run_type, run_id, "retry_requested")
            return True

    def _finish_execution(
        self,
        conn: sqlite3.Connection,
        run_type: str,
        run_id: int,
        lease_token: str,
        status: str,
        error: str = "",
    ) -> str | None:
        row = conn.execute(
            "SELECT status FROM execution_runs WHERE run_type = ? AND run_id = ? "
            "AND lease_token = ? AND lease_expires_at > CURRENT_TIMESTAMP",
            (run_type, run_id, lease_token),
        ).fetchone()
        if row is None or row["status"] not in {"running", "cancel_requested"}:
            return None
        final_status = "cancelled" if row["status"] == "cancel_requested" else status
        conn.execute(
            "UPDATE execution_runs SET status = ?, lease_token = '', worker_id = '', "
            "last_error = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
            "WHERE run_type = ? AND run_id = ?",
            (final_status, error[:1000], run_type, run_id),
        )
        return final_status

    def finish_improvement_run(
        self,
        improvement_id: int,
        lease_token: str,
        runner_status: str,
        execution_status: str = "completed",
        error: str = "",
    ) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            final_status = self._finish_execution(
                conn,
                "improvement",
                improvement_id,
                lease_token,
                execution_status,
                error,
            )
            if final_status is None:
                return False
            domain_status = "cancelled" if final_status == "cancelled" else runner_status
            cursor = conn.execute(
                "UPDATE improvement_tasks SET runner_status = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (domain_status, improvement_id),
            )
            return cursor.rowcount > 0

    def add_improvement_task(
        self,
        task_id: int,
        feedback_id: int = 0,
        repo: str = "",
        branch_name: str = "",
        scope: str = "",
        risk_level: str = "normal",
        approval_status: str = "pending",
        runner_status: str = "idle",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO improvement_tasks "
                "(task_id, feedback_id, repo, branch_name, scope, risk_level, "
                "approval_status, runner_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    feedback_id,
                    repo,
                    branch_name,
                    scope,
                    risk_level,
                    approval_status,
                    runner_status,
                ),
            )
            return int(cursor.lastrowid)

    def get_improvement_task(self, improvement_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, task_id, feedback_id, repo, branch_name, scope, risk_level, "
                "approval_status, runner_status, created_at, updated_at "
                "FROM improvement_tasks WHERE id = ?",
                (improvement_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_improvement_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, task_id, feedback_id, repo, branch_name, scope, risk_level, "
                "approval_status, runner_status, created_at, updated_at "
                "FROM improvement_tasks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_improvement_task(self, repo: str, scope: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, task_id, feedback_id, repo, branch_name, scope, risk_level, "
                "approval_status, runner_status, created_at, updated_at "
                "FROM improvement_tasks WHERE repo = ? AND scope = ? ORDER BY id DESC LIMIT 1",
                (repo, scope),
            ).fetchone()
        return dict(row) if row else None

    def update_improvement_task(
        self,
        improvement_id: int,
        approval_status: str | None = None,
        runner_status: str | None = None,
        branch_name: str | None = None,
    ) -> bool:
        fields: list[str] = []
        values: list[Any] = []
        if approval_status is not None:
            fields.append("approval_status = ?")
            values.append(approval_status)
        if runner_status is not None:
            fields.append("runner_status = ?")
            values.append(runner_status)
        if branch_name is not None:
            fields.append("branch_name = ?")
            values.append(branch_name)
        if not fields:
            return False
        fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(improvement_id)
        with self.connect() as conn:
            cursor = conn.execute(
                f"UPDATE improvement_tasks SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            return cursor.rowcount > 0

    def add_pull_request(
        self,
        improvement_task_id: int,
        github_owner: str,
        github_repo: str,
        number: int,
        url: str,
        branch_name: str,
        status: str = "open",
        checks_status: str = "unknown",
    ) -> int:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM pull_requests WHERE "
                "(? > 0 AND improvement_task_id = ?) "
                "OR (lower(github_owner) = lower(?) AND lower(github_repo) = lower(?) "
                "AND number = ?) "
                "ORDER BY id DESC LIMIT 1",
                (
                    improvement_task_id,
                    improvement_task_id,
                    github_owner,
                    github_repo,
                    number,
                ),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = conn.execute(
                "INSERT INTO pull_requests "
                "(improvement_task_id, github_owner, github_repo, number, url, "
                "branch_name, status, checks_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    improvement_task_id,
                    github_owner,
                    github_repo,
                    number,
                    url,
                    branch_name,
                    status,
                    checks_status,
                ),
            )
            return int(cursor.lastrowid)

    def get_pull_request(self, pr_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, improvement_task_id, github_owner, github_repo, number, url, "
                "branch_name, status, checks_status, merged_at, created_at, updated_at "
                "FROM pull_requests WHERE id = ?",
                (pr_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_pull_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, improvement_task_id, github_owner, github_repo, number, url, "
                "branch_name, status, checks_status, merged_at, created_at, updated_at "
                "FROM pull_requests ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_pull_request_for_improvement(
        self,
        improvement_task_id: int,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, improvement_task_id, github_owner, github_repo, number, url, "
                "branch_name, status, checks_status, merged_at, created_at, updated_at "
                "FROM pull_requests WHERE improvement_task_id = ? ORDER BY id DESC LIMIT 1",
                (improvement_task_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_pull_request_by_number(
        self,
        number: int,
        github_owner: str = "",
        github_repo: str = "",
    ) -> dict[str, Any] | None:
        clauses = ["number = ?"]
        values: list[Any] = [number]
        if github_owner:
            clauses.append("lower(github_owner) = lower(?)")
            values.append(github_owner)
        if github_repo:
            clauses.append("lower(github_repo) = lower(?)")
            values.append(github_repo)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, improvement_task_id, github_owner, github_repo, number, url, "
                "branch_name, status, checks_status, merged_at, created_at, updated_at "
                f"FROM pull_requests WHERE {' AND '.join(clauses)} "
                "ORDER BY id DESC LIMIT 1",
                values,
            ).fetchone()
        return dict(row) if row else None

    def get_latest_notified_open_pull_request(
        self,
        platform: str,
        recipient_id: str,
        github_owner: str = "",
        github_repo: str = "",
    ) -> dict[str, Any] | None:
        conditions = [
            "notifications.platform = ?",
            "notifications.recipient_id = ?",
            "notifications.status = 'sent'",
            "pull_requests.status = 'open'",
        ]
        values: list[Any] = [platform, recipient_id]
        if github_owner:
            conditions.append("pull_requests.github_owner = ?")
            values.append(github_owner)
        if github_repo:
            conditions.append("pull_requests.github_repo = ?")
            values.append(github_repo)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT pull_requests.id, pull_requests.improvement_task_id, "
                "pull_requests.github_owner, pull_requests.github_repo, "
                "pull_requests.number, pull_requests.url, pull_requests.branch_name, "
                "pull_requests.status, pull_requests.checks_status, "
                "pull_requests.merged_at, pull_requests.created_at, "
                "pull_requests.updated_at FROM owner_notifications AS notifications "
                "JOIN pull_requests ON notifications.dedupe_key = "
                "'pr:' || lower(pull_requests.github_owner) || '/' || "
                "lower(pull_requests.github_repo) || ':' || pull_requests.number || ':opened' "
                f"WHERE {' AND '.join(conditions)} "
                "ORDER BY notifications.id DESC, pull_requests.id DESC LIMIT 1",
                values,
            ).fetchone()
        return dict(row) if row else None

    def update_pull_request(
        self,
        pr_id: int,
        status: str | None = None,
        checks_status: str | None = None,
        merged_at: str | None = None,
        url: str | None = None,
        branch_name: str | None = None,
    ) -> bool:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if checks_status is not None:
            fields.append("checks_status = ?")
            values.append(checks_status)
        if merged_at is not None:
            fields.append("merged_at = ?")
            values.append(merged_at)
        if url is not None:
            fields.append("url = ?")
            values.append(url)
        if branch_name is not None:
            fields.append("branch_name = ?")
            values.append(branch_name)
        if not fields:
            return False
        fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(pr_id)
        with self.connect() as conn:
            cursor = conn.execute(
                f"UPDATE pull_requests SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            return cursor.rowcount > 0

    def begin_code_review(
        self,
        github_owner: str,
        github_repo: str,
        pr_number: int,
        pr_url: str,
        head_sha: str,
        worker_id: str = "local",
        lease_seconds: int = 120,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._recover_stale_executions(conn)
            row = conn.execute(
                "SELECT * FROM code_review_runs WHERE github_owner = ? "
                "AND github_repo = ? AND pr_number = ? AND head_sha = ?",
                (github_owner, github_repo, pr_number, head_sha),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    "INSERT INTO code_review_runs "
                    "(github_owner, github_repo, pr_number, pr_url, head_sha) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (github_owner, github_repo, pr_number, pr_url, head_sha),
                )
                review_id = int(cursor.lastrowid)
                is_new = True
            else:
                review_id = int(row["id"])
                execution = conn.execute(
                    "SELECT status FROM execution_runs WHERE run_type = 'code_review' "
                    "AND run_id = ?",
                    (review_id,),
                ).fetchone()
                resumable = str(row["status"]) in {"failed", "retry_requested", "stale"}
                if str(row["status"]) == "processing" and execution is None:
                    resumable = True
                if not resumable:
                    return None
                is_new = False
            claimed_execution = self._claim_execution(
                conn,
                "code_review",
                review_id,
                worker_id,
                lease_seconds,
            )
            if claimed_execution is None:
                return None
            if not is_new:
                conn.execute(
                    "UPDATE code_review_runs SET status = 'processing', "
                    "attempt_count = attempt_count + 1, pr_url = ?, last_error = '', "
                    "completed_at = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (pr_url, review_id),
                )
            claimed = conn.execute(
                "SELECT * FROM code_review_runs WHERE id = ?",
                (review_id,),
            ).fetchone()
        if claimed is None:
            return None
        result = dict(claimed)
        result["execution_token"] = claimed_execution["lease_token"]
        result["container_name"] = claimed_execution["container_name"]
        return result

    def complete_code_review(
        self,
        code_review_id: int,
        review_id: int,
        review_url: str,
        findings_count: int,
        summary: str,
        execution_token: str = "",
    ) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            final_status = "completed"
            if execution_token:
                finished = self._finish_execution(
                    conn,
                    "code_review",
                    code_review_id,
                    execution_token,
                    "completed",
                )
                if finished is None:
                    return False
                final_status = finished
            cursor = conn.execute(
                "UPDATE code_review_runs SET status = ?, review_id = ?, "
                "review_url = ?, findings_count = ?, summary = ?, last_error = '', "
                "updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (
                    final_status,
                    review_id,
                    review_url,
                    findings_count,
                    summary[:4000],
                    code_review_id,
                ),
            )
            return cursor.rowcount > 0

    def fail_code_review(
        self,
        code_review_id: int,
        error: str,
        execution_token: str = "",
    ) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            final_status = "failed"
            if execution_token:
                finished = self._finish_execution(
                    conn,
                    "code_review",
                    code_review_id,
                    execution_token,
                    "failed",
                    error,
                )
                if finished is None:
                    return False
                final_status = finished
            cursor = conn.execute(
                "UPDATE code_review_runs SET status = ?, last_error = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (final_status, error[:1000], code_review_id),
            )
            return cursor.rowcount > 0

    def cancel_code_review(self, code_review_id: int, execution_token: str) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            finished = self._finish_execution(
                conn,
                "code_review",
                code_review_id,
                execution_token,
                "cancelled",
                "cancelled by owner",
            )
            if finished is None:
                return False
            cursor = conn.execute(
                "UPDATE code_review_runs SET status = 'cancelled', "
                "last_error = 'cancelled by owner', completed_at = CURRENT_TIMESTAMP, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (code_review_id,),
            )
            return cursor.rowcount > 0

    def get_code_review(self, code_review_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM code_review_runs WHERE id = ?",
                (code_review_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_code_reviews(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM code_review_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def begin_github_issue(
        self,
        github_owner: str,
        github_repo: str,
        issue_number: int,
        issue_url: str,
        issue_updated_at: str,
        title: str,
        body: str,
        resume_worthwhile: bool = False,
        worker_id: str = "local",
        lease_seconds: int = 120,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._recover_stale_executions(conn)
            row = conn.execute(
                "SELECT * FROM github_issue_runs WHERE github_owner = ? "
                "AND github_repo = ? AND issue_number = ? AND issue_updated_at = ?",
                (github_owner, github_repo, issue_number, issue_updated_at),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    "INSERT INTO github_issue_runs "
                    "(github_owner, github_repo, issue_number, issue_url, issue_updated_at, "
                    "title, body) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        github_owner,
                        github_repo,
                        issue_number,
                        issue_url,
                        issue_updated_at,
                        title,
                        body,
                    ),
                )
                run_id = int(cursor.lastrowid)
                is_new = True
                allow_completed = False
            else:
                resumable_statuses = ["failed"]
                if resume_worthwhile:
                    resumable_statuses.append("worthwhile")
                resumable_statuses.extend(["retry_requested", "stale"])
                run_id = int(row["id"])
                execution = conn.execute(
                    "SELECT status FROM execution_runs WHERE run_type = 'github_issue' "
                    "AND run_id = ?",
                    (run_id,),
                ).fetchone()
                resumable = str(row["status"]) in resumable_statuses
                if str(row["status"]) == "processing" and execution is None:
                    resumable = True
                if not resumable:
                    return None
                is_new = False
                allow_completed = str(row["status"]) == "worthwhile"
            claimed_execution = self._claim_execution(
                conn,
                "github_issue",
                run_id,
                worker_id,
                lease_seconds,
                allow_completed=allow_completed,
            )
            if claimed_execution is None:
                return None
            if not is_new:
                conn.execute(
                    "UPDATE github_issue_runs SET status = 'processing', "
                    "attempt_count = attempt_count + 1, issue_url = ?, title = ?, body = ?, "
                    "last_error = '', completed_at = '', updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (issue_url, title, body, run_id),
                )
            claimed = conn.execute(
                "SELECT * FROM github_issue_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if claimed is None:
            return None
        result = dict(claimed)
        result["execution_token"] = claimed_execution["lease_token"]
        result["container_name"] = claimed_execution["container_name"]
        return result

    def complete_github_issue_evaluation(
        self,
        run_id: int,
        status: str,
        worthwhile: bool,
        confidence: float,
        rationale: str,
        implementation_summary: str,
        provider: str,
        model: str,
        execution_token: str = "",
    ) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            final_status = status
            if execution_token and status != "processing":
                finished = self._finish_execution(
                    conn,
                    "github_issue",
                    run_id,
                    execution_token,
                    "completed",
                )
                if finished is None:
                    return False
                if finished == "cancelled":
                    final_status = "cancelled"
            elif execution_token:
                execution = conn.execute(
                    "SELECT 1 FROM execution_runs WHERE run_type = 'github_issue' AND run_id = ? "
                    "AND lease_token = ? AND status = 'running'",
                    (run_id, execution_token),
                ).fetchone()
                if execution is None:
                    return False
            cursor = conn.execute(
                "UPDATE github_issue_runs SET status = ?, worthwhile = ?, confidence = ?, "
                "rationale = ?, implementation_summary = ?, provider = ?, model = ?, "
                "last_error = '', updated_at = CURRENT_TIMESTAMP, completed_at = "
                "CASE WHEN ? = 'processing' THEN '' ELSE CURRENT_TIMESTAMP END WHERE id = ?",
                (
                    final_status,
                    int(worthwhile),
                    confidence,
                    rationale[:4000],
                    implementation_summary[:4000],
                    provider,
                    model,
                    final_status,
                    run_id,
                ),
            )
            return cursor.rowcount > 0

    def link_github_issue_improvement(
        self,
        run_id: int,
        improvement_task_id: int,
        execution_token: str = "",
    ) -> bool:
        with self.connect() as conn:
            if execution_token:
                execution = conn.execute(
                    "SELECT 1 FROM execution_runs WHERE run_type = 'github_issue' AND run_id = ? "
                    "AND lease_token = ? AND status = 'running'",
                    (run_id, execution_token),
                ).fetchone()
                if execution is None:
                    return False
            cursor = conn.execute(
                "UPDATE github_issue_runs SET improvement_task_id = ?, status = 'processing', "
                "completed_at = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (improvement_task_id, run_id),
            )
            return cursor.rowcount > 0

    def complete_github_issue_run(
        self,
        run_id: int,
        status: str,
        pr_number: int = 0,
        pr_url: str = "",
        execution_token: str = "",
    ) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            final_status = status
            if execution_token:
                finished = self._finish_execution(
                    conn,
                    "github_issue",
                    run_id,
                    execution_token,
                    "completed",
                )
                if finished is None:
                    return False
                if finished == "cancelled":
                    final_status = "cancelled"
            cursor = conn.execute(
                "UPDATE github_issue_runs SET status = ?, pr_number = ?, pr_url = ?, "
                "last_error = '', updated_at = CURRENT_TIMESTAMP, "
                "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (final_status, pr_number, pr_url, run_id),
            )
            return cursor.rowcount > 0

    def fail_github_issue_run(
        self,
        run_id: int,
        error: str,
        execution_token: str = "",
    ) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            final_status = "failed"
            if execution_token:
                finished = self._finish_execution(
                    conn,
                    "github_issue",
                    run_id,
                    execution_token,
                    "failed",
                    error,
                )
                if finished is None:
                    return False
                final_status = finished
            cursor = conn.execute(
                "UPDATE github_issue_runs SET status = ?, last_error = ?, "
                "completed_at = CASE WHEN ? = 'cancelled' THEN CURRENT_TIMESTAMP ELSE '' END, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (final_status, error[:1000], final_status, run_id),
            )
            return cursor.rowcount > 0

    def cancel_github_issue_run(self, run_id: int, execution_token: str) -> bool:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            finished = self._finish_execution(
                conn,
                "github_issue",
                run_id,
                execution_token,
                "cancelled",
                "cancelled by owner",
            )
            if finished is None:
                return False
            cursor = conn.execute(
                "UPDATE github_issue_runs SET status = 'cancelled', "
                "last_error = 'cancelled by owner', completed_at = CURRENT_TIMESTAMP, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (run_id,),
            )
            return cursor.rowcount > 0

    def list_github_issue_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM github_issue_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_automation_cursor(self, name: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM automation_cursors WHERE name = ?",
                (name,),
            ).fetchone()
        return str(row["value"]) if row else ""

    def set_automation_cursor(self, name: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO automation_cursors (name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value, "
                "updated_at = CURRENT_TIMESTAMP",
                (name, value),
            )

    def upsert_merge_authorization(
        self,
        pull_request_id: int,
        decision: str,
        status: str,
        actor_platform: str,
        actor_source: str,
        actor_user_id: str,
        command: str = "",
        detail: str = "",
        authorized_head_sha: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO merge_authorizations "
                "(pull_request_id, decision, status, authorized_head_sha, actor_platform, "
                "actor_source, actor_user_id, command, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(pull_request_id) DO UPDATE SET decision = excluded.decision, "
                "status = excluded.status, authorized_head_sha = excluded.authorized_head_sha, "
                "actor_platform = excluded.actor_platform, "
                "actor_source = excluded.actor_source, actor_user_id = excluded.actor_user_id, "
                "command = excluded.command, detail = excluded.detail, "
                "updated_at = CURRENT_TIMESTAMP",
                (
                    pull_request_id,
                    decision,
                    status,
                    authorized_head_sha,
                    actor_platform,
                    actor_source,
                    actor_user_id,
                    command,
                    detail,
                ),
            )

    def claim_merge_authorization(
        self,
        pull_request_id: int,
        authorized_head_sha: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE merge_authorizations SET status = 'merging', detail = '', "
                "updated_at = CURRENT_TIMESTAMP WHERE pull_request_id = ? "
                "AND decision = 'approved' AND authorized_head_sha = ? AND "
                "(status IN ('approved', 'merge_pending') OR "
                "(status = 'merging' AND updated_at < datetime('now', '-2 minutes')))",
                (pull_request_id, authorized_head_sha),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT pull_request_id, decision, status, authorized_head_sha, "
                "actor_platform, actor_source, actor_user_id, command, detail, "
                "created_at, updated_at FROM merge_authorizations WHERE pull_request_id = ?",
                (pull_request_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_merge_authorization(self, pull_request_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT pull_request_id, decision, status, authorized_head_sha, actor_platform, "
                "actor_source, actor_user_id, command, detail, created_at, updated_at "
                "FROM merge_authorizations WHERE pull_request_id = ?",
                (pull_request_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_merge_authorizations(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT pull_request_id, decision, status, authorized_head_sha, actor_platform, "
                "actor_source, actor_user_id, command, detail, created_at, updated_at "
                "FROM merge_authorizations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_improvement_reflection(
        self,
        improvement_task_id: int,
        pull_request_id: int,
        outcome: str,
        summary: str,
        lessons: str = "",
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO improvement_reflections "
                "(improvement_task_id, pull_request_id, outcome, summary, lessons) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(pull_request_id) DO UPDATE SET "
                "outcome = excluded.outcome, summary = excluded.summary, "
                "lessons = excluded.lessons, updated_at = CURRENT_TIMESTAMP",
                (improvement_task_id, pull_request_id, outcome, summary, lessons),
            )
            row = conn.execute(
                "SELECT id FROM improvement_reflections WHERE pull_request_id = ?",
                (pull_request_id,),
            ).fetchone()
        return int(row["id"])

    def list_improvement_reflections(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, improvement_task_id, pull_request_id, outcome, summary, lessons, "
                "created_at, updated_at FROM improvement_reflections "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_deployment_record(
        self,
        pull_request_id: int,
        environment: str,
        target_revision: str,
        status: str = "pending",
        detail: str = "",
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO deployment_records "
                "(pull_request_id, environment, target_revision, status, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (pull_request_id, environment, target_revision, status, detail),
            )
            row = conn.execute(
                "SELECT id FROM deployment_records WHERE pull_request_id = ? "
                "AND environment = ? AND target_revision = ?",
                (pull_request_id, environment, target_revision),
            ).fetchone()
        return int(row["id"])

    def list_deployment_records(
        self,
        limit: int = 50,
        status: str | None = None,
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, pull_request_id, environment, target_revision, deployed_revision, "
            "status, detail, created_at, updated_at, deployed_at FROM deployment_records"
        )
        conditions: list[str] = []
        values: list[Any] = []
        if status:
            conditions.append("status = ?")
            values.append(status)
        if environment:
            conditions.append("environment = ?")
            values.append(environment)
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        query += " ORDER BY id DESC LIMIT ?"
        values.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def mark_deployment_record(
        self,
        deployment_id: int,
        status: str,
        deployed_revision: str = "",
        detail: str = "",
    ) -> bool:
        deployed_at = "CURRENT_TIMESTAMP" if status == "deployed" else "''"
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE deployment_records SET status = ?, deployed_revision = ?, "
                f"detail = ?, deployed_at = {deployed_at}, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (status, deployed_revision, detail, deployment_id),
            )
            return cursor.rowcount > 0

    def queue_owner_notification(
        self,
        dedupe_key: str,
        event_type: str,
        platform: str,
        recipient_id: str,
        content: str,
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO owner_notifications "
                "(dedupe_key, event_type, platform, recipient_id, content) "
                "VALUES (?, ?, ?, ?, ?)",
                (dedupe_key, event_type, platform, recipient_id, content),
            )
            row = conn.execute(
                "SELECT id FROM owner_notifications WHERE dedupe_key = ? "
                "AND platform = ? AND recipient_id = ?",
                (dedupe_key, platform, recipient_id),
            ).fetchone()
        return int(row["id"])

    def claim_owner_notification(
        self,
        notification_id: int,
        lease_seconds: int = 300,
    ) -> dict[str, Any] | None:
        stale_before = f"-{max(1, lease_seconds)} seconds"
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE owner_notifications SET status = 'sending', attempts = attempts + 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ? "
                "AND (status IN ('pending', 'failed') OR "
                "(status = 'sending' AND updated_at < datetime('now', ?)))",
                (notification_id, stale_before),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT id, dedupe_key, event_type, platform, recipient_id, content, "
                "status, attempts, last_error, sent_at, created_at, updated_at "
                "FROM owner_notifications WHERE id = ?",
                (notification_id,),
            ).fetchone()
        return dict(row) if row else None

    def finish_owner_notification(
        self,
        notification_id: int,
        status: str,
        last_error: str = "",
    ) -> bool:
        sent_at = "CURRENT_TIMESTAMP" if status == "sent" else "''"
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE owner_notifications SET status = ?, last_error = ?, "
                f"sent_at = {sent_at}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, last_error, notification_id),
            )
            return cursor.rowcount > 0

    def list_owner_notifications(
        self,
        limit: int = 50,
        retryable_only: bool = False,
        lease_seconds: int = 300,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, dedupe_key, event_type, platform, recipient_id, content, status, "
            "attempts, last_error, sent_at, created_at, updated_at FROM owner_notifications"
        )
        values: list[Any] = []
        if retryable_only:
            query += (
                " WHERE status IN ('pending', 'failed') OR "
                "(status = 'sending' AND updated_at < datetime('now', ?))"
            )
            values.append(f"-{max(1, lease_seconds)} seconds")
        query += " ORDER BY id ASC LIMIT ?"
        values.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def add_outbound_draft(
        self,
        conversation_id: str,
        actor_source: str,
        actor_user_id: str,
        target: str,
        recipient_user_id: str,
        recipient_label: str,
        content: str,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO outbound_drafts "
                "(conversation_id, actor_source, actor_user_id, target, recipient_user_id, "
                "recipient_label, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    actor_source,
                    actor_user_id,
                    target,
                    recipient_user_id,
                    recipient_label,
                    content,
                ),
            )
            return int(cursor.lastrowid)

    def get_outbound_draft(self, draft_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, conversation_id, actor_source, actor_user_id, target, "
                "recipient_user_id, recipient_label, content, status, expires_at, "
                "created_at, updated_at FROM outbound_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_outbound_draft_status(self, draft_id: int, status: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE outbound_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, draft_id),
            )
            return cursor.rowcount > 0

    def claim_outbound_draft(
        self,
        draft_id: int,
        actor_user_id: str,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE outbound_drafts SET status = 'sending', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND actor_user_id = ? "
                "AND conversation_id = ? AND status = 'pending' "
                "AND expires_at > CURRENT_TIMESTAMP",
                (draft_id, actor_user_id, conversation_id),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT id, conversation_id, actor_source, actor_user_id, target, "
                "recipient_user_id, recipient_label, content, status, expires_at, "
                "created_at, updated_at FROM outbound_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_outbound_drafts(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, actor_source, actor_user_id, target, "
                "recipient_user_id, recipient_label, content, status, expires_at, "
                "created_at, updated_at FROM outbound_drafts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_inbound_event(self, platform: str, event_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT platform, event_id, status, reply, result_json, last_error, "
                "created_at, updated_at FROM inbound_events WHERE platform = ? AND event_id = ?",
                (platform, event_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["result"] = json.loads(result["result_json"]) if result["result_json"] else {}
        return result

    def begin_inbound_event(self, platform: str, event_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO inbound_events (platform, event_id) VALUES (?, ?)",
                (platform, event_id),
            )
        result = self.get_inbound_event(platform, event_id)
        return result or {"platform": platform, "event_id": event_id, "status": "processing"}

    def save_inbound_event_reply(
        self,
        platform: str,
        event_id: str,
        reply: str,
        result: dict[str, object],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE inbound_events SET status = 'reply_ready', reply = ?, result_json = ?, "
                "last_error = '', updated_at = CURRENT_TIMESTAMP "
                "WHERE platform = ? AND event_id = ?",
                (reply, json.dumps(result, ensure_ascii=False), platform, event_id),
            )

    def complete_inbound_event(
        self,
        platform: str,
        event_id: str,
        result: dict[str, object],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE inbound_events SET status = 'completed', result_json = ?, "
                "last_error = '', updated_at = CURRENT_TIMESTAMP "
                "WHERE platform = ? AND event_id = ?",
                (json.dumps(result, ensure_ascii=False), platform, event_id),
            )

    def fail_inbound_event(self, platform: str, event_id: str, error: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE inbound_events SET last_error = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE platform = ? AND event_id = ?",
                (error[:1000], platform, event_id),
            )

    def add_feedback(self, source: str, user_id: str, content: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO feedbacks (source, user_id, content) VALUES (?, ?, ?)",
                (source, user_id, content),
            )
            return int(cursor.lastrowid)

    def get_feedback(self, feedback_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, source, user_id, content, status, created_at "
                "FROM feedbacks WHERE id = ?",
                (feedback_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_feedbacks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, source, user_id, content, status, created_at "
                "FROM feedbacks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_feedback_status(self, feedback_id: int, status: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE feedbacks SET status = ? WHERE id = ?",
                (status, feedback_id),
            )
            return cursor.rowcount > 0

    def count_messages(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def count_feedbacks(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM feedbacks").fetchone()[0])

    def count_memory_items(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0])

    def count_conversation_summaries(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()[0])

    def count_access_rules(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM access_rules").fetchone()[0])

    def count_audit_logs(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0])

    def table_counts(self) -> list[dict[str, Any]]:
        table_names = [
            "messages",
            "feedbacks",
            "memory_items",
            "conversation_summaries",
            "persons",
            "channel_accounts",
            "account_link_codes",
            "access_rules",
            "audit_logs",
            "tasks",
            "improvement_tasks",
            "pull_requests",
            "code_review_runs",
            "github_issue_runs",
            "execution_runs",
            "merge_authorizations",
            "improvement_reflections",
            "deployment_records",
            "owner_notifications",
            "outbound_drafts",
            "inbound_events",
            "automation_cursors",
        ]
        with self.connect() as conn:
            return [
                {
                    "table": table_name,
                    "rows": int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]),
                }
                for table_name in table_names
            ]
