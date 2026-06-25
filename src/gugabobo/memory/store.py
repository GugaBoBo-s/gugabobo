from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    def add_message(self, source: str, user_id: str, role: str, content: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (source, user_id, role, content) VALUES (?, ?, ?, ?)",
                (source, user_id, role, content),
            )
            return int(cursor.lastrowid)

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

    def count_messages(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def count_feedbacks(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM feedbacks").fetchone()[0])

