from __future__ import annotations

import os
import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from gugabobo.config import Settings, get_settings
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.memory.store import MemoryStore


class ExecutionStopped(RuntimeError):
    pass


class ExecutionCancelled(ExecutionStopped):
    pass


class ExecutionLeaseLost(ExecutionStopped):
    pass


def execution_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def recover_stale_execution_containers(
    store: MemoryStore,
    settings: Settings | None = None,
) -> int:
    records = store.recover_stale_execution_records()
    if not records:
        return 0
    runtime = ContainerRuntime(settings or get_settings())
    for record in records:
        container_name = str(record.get("container_name", ""))
        if container_name:
            runtime.stop(container_name)
    return len(records)


@dataclass
class ExecutionLease:
    store: MemoryStore
    run_type: str
    run_id: int
    token: str
    lease_seconds: int
    heartbeat_seconds: int
    container_name: str
    _shutdown: threading.Event = field(default_factory=threading.Event, init=False)
    _stopped: threading.Event = field(default_factory=threading.Event, init=False)
    _cancelled: bool = field(default=False, init=False)

    @classmethod
    def from_claim(
        cls,
        store: MemoryStore,
        run_type: str,
        run_id: int,
        claim: dict[str, object],
        lease_seconds: int,
        heartbeat_seconds: int,
    ) -> ExecutionLease:
        return cls(
            store=store,
            run_type=run_type,
            run_id=run_id,
            token=str(claim["lease_token"]),
            lease_seconds=lease_seconds,
            heartbeat_seconds=min(heartbeat_seconds, max(1, lease_seconds // 3)),
            container_name=str(claim["container_name"]),
        )

    def pulse(self) -> bool:
        if self._stopped.is_set():
            return False
        if self.store.heartbeat_execution(
            self.run_type,
            self.run_id,
            self.token,
            self.lease_seconds,
        ):
            return True
        state = self.store.get_execution_run(self.run_type, self.run_id) or {}
        self._cancelled = str(state.get("status", "")) in {
            "cancel_requested",
            "cancelled",
        }
        self._stopped.set()
        return False

    def ensure_active(self) -> None:
        if self.pulse():
            return
        if self._cancelled:
            raise ExecutionCancelled(f"{self.run_type} #{self.run_id} was cancelled")
        raise ExecutionLeaseLost(f"{self.run_type} #{self.run_id} lease was lost")

    @contextmanager
    def keepalive(self) -> Iterator[ExecutionLease]:
        self.ensure_active()
        thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        thread.start()
        try:
            yield self
        finally:
            self._shutdown.set()
            thread.join(timeout=max(1, self.heartbeat_seconds + 1))

    def _heartbeat_loop(self) -> None:
        while not self._shutdown.wait(self.heartbeat_seconds):
            if not self.pulse():
                return


@dataclass(frozen=True)
class ExecutionMonitorGroup:
    leases: tuple[ExecutionLease, ...]

    @property
    def container_name(self) -> str:
        return self.leases[0].container_name

    def pulse(self) -> bool:
        return all(lease.pulse() for lease in self.leases)

    def ensure_active(self) -> None:
        for lease in self.leases:
            lease.ensure_active()
