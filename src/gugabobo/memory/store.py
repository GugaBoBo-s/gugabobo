from __future__ import annotations

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
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        detail: str = "",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO audit_logs "
                "(actor_source, actor_user_id, action, target, status, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (actor_source, actor_user_id, action, target, status, detail),
            )
            return int(cursor.lastrowid)

    def list_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, actor_source, actor_user_id, action, target, status, detail, "
                "created_at FROM audit_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_feedback(self, source: str, user_id: str, content: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO feedbacks (source, user_id, content) VALUES (?, ?, ?)",
                (source, user_id, content),
            )
            return int(cursor.lastrowid)

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
        ]
        with self.connect() as conn:
            return [
                {
                    "table": table_name,
                    "rows": int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]),
                }
                for table_name in table_names
            ]
