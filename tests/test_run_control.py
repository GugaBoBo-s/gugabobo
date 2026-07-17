import pytest

from gugabobo.core.run_control import (
    ExecutionCancelled,
    ExecutionLease,
    recover_stale_execution_containers,
)
from gugabobo.memory.store import MemoryStore


def add_improvement(store: MemoryStore) -> int:
    task_id = store.add_task("Improve recovery")
    return store.add_improvement_task(
        task_id,
        approval_status="approved",
        runner_status="idle",
    )


def claim(store: MemoryStore, improvement_id: int, worker: str = "worker-a") -> dict:
    result = store.claim_improvement_run(improvement_id, worker, 120)
    assert result is not None
    return result


def test_cancelled_execution_stops_lease_and_updates_domain_status(tmp_path) -> None:
    store = MemoryStore(tmp_path / "runs.db")
    improvement_id = add_improvement(store)
    record = claim(store, improvement_id)
    lease = ExecutionLease.from_claim(
        store,
        "improvement",
        improvement_id,
        record,
        120,
        15,
    )

    requested = store.request_execution_cancel("improvement", improvement_id)

    assert requested is not None
    with pytest.raises(ExecutionCancelled):
        lease.ensure_active()
    assert store.finish_improvement_run(
        improvement_id,
        lease.token,
        "cancelled",
        "cancelled",
    )
    assert store.get_execution_run("improvement", improvement_id)["status"] == "cancelled"
    assert store.get_improvement_task(improvement_id)["runner_status"] == "cancelled"


def test_expired_execution_is_recovered_and_reclaimed(tmp_path) -> None:
    store = MemoryStore(tmp_path / "runs.db")
    improvement_id = add_improvement(store)
    first = claim(store, improvement_id)
    with store.connect() as conn:
        conn.execute(
            "UPDATE execution_runs SET lease_expires_at = datetime('now', '-1 second') "
            "WHERE run_type = 'improvement' AND run_id = ?",
            (improvement_id,),
        )

    assert store.recover_stale_executions() == 1
    assert store.get_improvement_task(improvement_id)["runner_status"] == "stale"
    second = claim(store, improvement_id, "worker-b")

    assert second["lease_token"] != first["lease_token"]
    assert second["attempt_count"] == 2
    assert store.get_improvement_task(improvement_id)["runner_status"] == "running"


def test_stale_worker_cannot_overwrite_new_execution(tmp_path) -> None:
    store = MemoryStore(tmp_path / "runs.db")
    improvement_id = add_improvement(store)
    first = claim(store, improvement_id)
    with store.connect() as conn:
        conn.execute(
            "UPDATE execution_runs SET lease_expires_at = datetime('now', '-1 second') "
            "WHERE run_type = 'improvement' AND run_id = ?",
            (improvement_id,),
        )
    store.recover_stale_executions()
    second = claim(store, improvement_id, "worker-b")

    assert not store.finish_improvement_run(
        improvement_id,
        str(first["lease_token"]),
        "failed",
        "failed",
    )
    assert store.get_execution_run("improvement", improvement_id)["lease_token"] == second[
        "lease_token"
    ]
    assert store.get_improvement_task(improvement_id)["runner_status"] == "running"


def test_cancelled_execution_requires_explicit_retry(tmp_path) -> None:
    store = MemoryStore(tmp_path / "runs.db")
    improvement_id = add_improvement(store)
    first = claim(store, improvement_id)
    store.request_execution_cancel("improvement", improvement_id)
    store.finish_improvement_run(
        improvement_id,
        str(first["lease_token"]),
        "cancelled",
        "cancelled",
    )

    assert store.claim_improvement_run(improvement_id, "worker-b", 120) is None
    assert store.request_execution_retry("improvement", improvement_id)
    retried = claim(store, improvement_id, "worker-b")

    assert retried["attempt_count"] == 2
    assert store.get_improvement_task(improvement_id)["runner_status"] == "running"


def test_stale_recovery_stops_orphaned_container(tmp_path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "runs.db")
    improvement_id = add_improvement(store)
    record = claim(store, improvement_id)
    stopped = []
    monkeypatch.setattr(
        "gugabobo.core.run_control.ContainerRuntime.stop",
        lambda self, container_name: stopped.append(container_name) or True,
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE execution_runs SET lease_expires_at = datetime('now', '-1 second') "
            "WHERE run_type = 'improvement' AND run_id = ?",
            (improvement_id,),
        )

    assert recover_stale_execution_containers(store) == 1
    assert stopped == [record["container_name"]]
