import sqlite3
import threading
import time

import pytest

from gugabobo.memory import store as store_module
from gugabobo.memory.store import MemoryStore


def test_connections_use_wal_and_configured_busy_timeout(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", busy_timeout_ms=1234)

    with store.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout == 1234


def test_write_retries_until_another_connection_releases_lock(tmp_path):
    db_path = tmp_path / "locked.db"
    store = MemoryStore(
        db_path,
        busy_timeout_ms=10,
        lock_retry_attempts=5,
        retry_delay_seconds=0.01,
    )
    blocker = sqlite3.connect(db_path, check_same_thread=False)
    blocker.execute("BEGIN IMMEDIATE")
    lock_released = threading.Event()

    def release_lock() -> None:
        time.sleep(0.06)
        blocker.commit()
        blocker.close()
        lock_released.set()

    release_thread = threading.Thread(target=release_lock)
    release_thread.start()
    try:
        feedback_id = store.add_feedback("test", "user", "retry me")
    finally:
        release_thread.join(timeout=1)
        if not lock_released.is_set():
            blocker.close()

    assert lock_released.is_set()
    assert store.get_feedback(feedback_id)["content"] == "retry me"


def test_non_lock_operational_errors_are_not_retried(tmp_path, monkeypatch):
    store = MemoryStore(
        tmp_path / "errors.db",
        busy_timeout_ms=1,
        lock_retry_attempts=3,
        retry_delay_seconds=0.01,
    )
    sleep_calls = []
    monkeypatch.setattr(store_module.time, "sleep", sleep_calls.append)

    with (
        store.connect() as conn,
        pytest.raises(sqlite3.OperationalError, match="no such table"),
    ):
        conn.execute("SELECT * FROM missing_table")

    assert sleep_calls == []


def test_write_stops_after_configured_lock_retries(tmp_path, monkeypatch):
    db_path = tmp_path / "persistent-lock.db"
    store = MemoryStore(
        db_path,
        busy_timeout_ms=1,
        lock_retry_attempts=2,
        retry_delay_seconds=0.01,
    )
    blocker = sqlite3.connect(db_path)
    blocker.execute("BEGIN IMMEDIATE")
    sleep_calls = []
    monkeypatch.setattr(store_module.time, "sleep", sleep_calls.append)

    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.add_feedback("test", "user", "stay locked")
    finally:
        blocker.rollback()
        blocker.close()

    assert sleep_calls == [0.01, 0.02]


def test_concurrent_initialization_serializes_legacy_migrations(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE access_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, user_id)
            );
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_source TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE merge_authorizations (
                pull_request_id INTEGER PRIMARY KEY,
                decision TEXT NOT NULL,
                status TEXT NOT NULL,
                actor_platform TEXT NOT NULL,
                actor_source TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                command TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    start = threading.Barrier(2)
    errors = []

    def initialize() -> None:
        start.wait()
        try:
            MemoryStore(
                db_path,
                busy_timeout_ms=5,
                lock_retry_attempts=7,
                retry_delay_seconds=0.01,
            )
        except sqlite3.Error as error:
            errors.append(error)

    threads = [threading.Thread(target=initialize) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    with sqlite3.connect(db_path) as conn:
        message_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        access_rule_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(access_rules)").fetchall()
        }

    assert "conversation_id" in message_columns
    assert {"display_name", "notes", "updated_at"} <= access_rule_columns
