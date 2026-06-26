import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from gugabobo.config import get_settings
from gugabobo.core.agent import CoreAgent
from gugabobo.memory.store import MemoryStore


def build_agent() -> CoreAgent:
    settings = get_settings()
    store = MemoryStore(settings.db_path)
    return CoreAgent(store)


class RuntimeManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.runtime_path = self.settings.data_dir / "runtime.json"

    def status(self) -> dict[str, object]:
        state = self._read_state()
        telegram_pid = self._pid_value(state.get("telegram_polling_pid"))
        telegram_running = bool(telegram_pid and self._process_exists(telegram_pid))
        if telegram_pid and not telegram_running:
            state.pop("telegram_polling_pid", None)
            self._write_state(state)
        return {
            "api": {
                "running": True,
                "pid": os.getpid(),
                "host": self.settings.api_host,
                "port": self.settings.api_port,
            },
            "telegram_polling": {
                "running": telegram_running,
                "pid": telegram_pid if telegram_running else None,
                "configured": bool(self.settings.telegram_bot_token),
                "reply_enabled": self.settings.telegram_reply_enabled,
                "bot_username": self.settings.telegram_bot_username,
            },
            "napcat": {
                "api_url": self.settings.napcat_api_url,
                "reply_enabled": self.settings.napcat_reply_enabled,
                "passive_reply_enabled": self.settings.napcat_passive_reply_enabled,
                "access_token_configured": bool(self.settings.napcat_access_token),
            },
        }

    def start_telegram_polling(self) -> dict[str, object]:
        status = self.status()
        current = status["telegram_polling"]
        if current["running"]:
            return {"status": "already_running", "pid": current["pid"]}
        if not self.settings.telegram_bot_token:
            return {"status": "not_configured", "pid": None}
        command = [
            sys.executable,
            "-m",
            "gugabobo.main",
            "telegram",
            "poll",
            "--send",
        ]
        process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )
        state = self._read_state()
        state["telegram_polling_pid"] = process.pid
        self._write_state(state)
        return {"status": "started", "pid": process.pid}

    def stop_telegram_polling(self) -> dict[str, object]:
        state = self._read_state()
        pid = self._pid_value(state.get("telegram_polling_pid"))
        if not pid or not self._process_exists(pid):
            state.pop("telegram_polling_pid", None)
            self._write_state(state)
            return {"status": "not_running", "pid": None}
        self._terminate_process(pid)
        state.pop("telegram_polling_pid", None)
        self._write_state(state)
        return {"status": "stopped", "pid": pid}

    def _read_state(self) -> dict[str, object]:
        if not self.runtime_path.exists():
            return {}
        try:
            return json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_state(self, state: dict[str, object]) -> None:
        self.runtime_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _pid_value(self, value: object) -> int | None:
        try:
            pid = int(value)
        except (TypeError, ValueError):
            return None
        return pid if pid > 0 else None

    def _process_exists(self, pid: int) -> bool:
        if os.name == "nt":
            return self._windows_process_exists(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _windows_process_exists(self, pid: int) -> bool:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        return f'"{pid}"' in result.stdout or f",{pid}," in result.stdout

    def _terminate_process(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
            return
        os.kill(pid, signal.SIGTERM)

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
