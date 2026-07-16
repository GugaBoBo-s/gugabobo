from __future__ import annotations

import json
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
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ? AND id > ?",
                (conversation_id, after_message_id),
            ).fetchone()
        return int(row["c"]) if row else 0

    def delete_conversation_messages(self, conversation_id: str) -> int:
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

    def update_pull_request(
        self,
        pr_id: int,
        status: str | None = None,
        checks_status: str | None = None,
        merged_at: str | None = None,
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
            "access_rules",
            "audit_logs",
            "tasks",
            "improvement_tasks",
            "pull_requests",
            "outbound_drafts",
            "inbound_events",
        ]
        with self.connect() as conn:
            return [
                {
                    "table": table_name,
                    "rows": int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]),
                }
                for table_name in table_names
            ]
