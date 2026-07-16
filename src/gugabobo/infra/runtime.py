import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from gugabobo.config import get_settings
from gugabobo.core.agent import CoreAgent
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.infra.telegram_client import TelegramClient
from gugabobo.memory.store import MemoryStore


def build_agent(background_summarize: bool = True) -> CoreAgent:
    settings = get_settings()
    store = MemoryStore(settings.db_path)
    agent = CoreAgent(store)
    agent.background_summarize = background_summarize
    return agent


class RuntimeManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.runtime_path = self.settings.data_dir / "runtime.json"

    def status(self) -> dict[str, object]:
        state = self._read_state()
        container_runtime = ContainerRuntime(self.settings)
        runner_runtime_configured = container_runtime.configured
        runner_image_available = (
            container_runtime.image_available if runner_runtime_configured else False
        )
        telegram_status = self._telegram_polling_status(state)
        lifecycle_pid = self._external_lifecycle_pid()
        return {
            "api": {
                "running": True,
                "pid": os.getpid(),
                "host": self.settings.api_host,
                "port": self.settings.api_port,
            },
            "telegram_polling": {
                **telegram_status,
                "configured": bool(self.settings.telegram_bot_token),
                "reply_enabled": self.settings.telegram_reply_enabled,
                "bot_username": self.settings.telegram_bot_username,
            },
            "lifecycle_agent": {
                "running": lifecycle_pid is not None,
                "pid": lifecycle_pid,
                "github_configured": bool(self.settings.github_token),
            },
            "napcat": {
                "api_url": self.settings.napcat_api_url,
                "reply_enabled": self.settings.napcat_reply_enabled,
                "passive_reply_enabled": self.settings.napcat_passive_reply_enabled,
                "access_token_configured": bool(self.settings.napcat_access_token),
                **self._napcat_process_status(),
            },
            "self_improvement": {
                "runtime": self.settings.runner_container_runtime,
                "runtime_configured": runner_runtime_configured,
                "image": self.settings.runner_container_image,
                "image_available": runner_image_available,
                "github_configured": bool(self.settings.github_token),
                "claude_base_url": self.settings.claude_base_url,
                "claude_gateway_configured": bool(
                    self.settings.claude_base_url and self.settings.claude_auth_token
                ),
            },
        }

    def qq_diagnostics(self, store: MemoryStore) -> dict[str, object]:
        webui = self._tcp_status("127.0.0.1", 6099)
        napcat_api_url = self.settings.napcat_api_url
        napcat_api = self._url_tcp_status(napcat_api_url)
        qq_messages = store.list_messages_by_source_prefix("qq_", limit=1)
        reply_mode = self._qq_reply_mode()
        return {
            "api": {
                "running": True,
                "pid": os.getpid(),
                "onebot_url": f"http://{self.settings.api_host}:{self.settings.api_port}/onebot/v11/events",
            },
            "napcat_webui": webui,
            "napcat_api": {
                **napcat_api,
                "url": napcat_api_url,
            },
            "napcat_process": self._napcat_process_status(),
            "reply_mode": reply_mode,
            "settings": {
                "napcat_reply_enabled": self.settings.napcat_reply_enabled,
                "napcat_passive_reply_enabled": self.settings.napcat_passive_reply_enabled,
                "qq_group_wake_words": self.settings.qq_group_wake_words,
            },
            "last_qq_message": qq_messages[0] if qq_messages else None,
            "checks": self._qq_checks(webui, napcat_api, reply_mode),
        }

    def telegram_diagnostics(
        self,
        store: MemoryStore,
        runtime_status: dict[str, object] | None = None,
    ) -> dict[str, object]:
        polling_status = runtime_status or self.status()["telegram_polling"]
        telegram_messages = store.list_messages_by_source_prefix("telegram_", limit=1)
        configured = bool(self.settings.telegram_bot_token)
        return {
            "configured": configured,
            "bot_username": self.settings.telegram_bot_username,
            "polling": polling_status,
            "reply_enabled": self.settings.telegram_reply_enabled,
            "group_wake_words": self.settings.telegram_group_wake_words,
            "last_telegram_message": telegram_messages[0] if telegram_messages else None,
            "checks": [
                {
                    "name": "Telegram token",
                    "ok": configured,
                    "detail": "GUGABOBO_TELEGRAM_BOT_TOKEN",
                },
                {
                    "name": "Telegram polling",
                    "ok": bool(polling_status["running"]),
                    "detail": "local getUpdates polling",
                },
                {
                    "name": "Telegram replies",
                    "ok": self.settings.telegram_reply_enabled,
                    "detail": "GUGABOBO_TELEGRAM_REPLY_ENABLED",
                },
            ],
        }

    def telegram_get_me(self) -> dict[str, object]:
        if not self.settings.telegram_bot_token:
            return {"status": "not_configured", "ok": False}
        try:
            me = TelegramClient().get_me()
        except Exception as error:
            return {"status": "error", "ok": False, "error": str(error)}
        return {"status": "ok", "ok": True, "bot": me}

    def start_napcat(self) -> dict[str, object]:
        status = self._napcat_process_status()
        if status["running"]:
            return {"status": "already_running", "pids": status["pids"]}
        quick_bat = self.settings.napcat_dir / "napcat.quick.bat"
        if not quick_bat.exists():
            return {
                "status": "not_configured",
                "reason": f"{quick_bat} not found",
                "pids": [],
            }
        subprocess.Popen(
            ["cmd", "/c", str(quick_bat)],
            cwd=self.settings.napcat_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )
        return {"status": "started", "pids": []}

    def stop_napcat(self) -> dict[str, object]:
        status = self._napcat_process_status()
        pids = [int(pid) for pid in status["pids"]]
        if not pids:
            return {"status": "not_running", "pids": []}
        for pid in pids:
            self._terminate_process(pid)
        return {"status": "stopped", "pids": pids}

    def napcat_webui_url(self) -> dict[str, object]:
        webui_config = self._napcat_webui_config()
        token = str(webui_config.get("token", ""))
        port = int(webui_config.get("port", 6099) or 6099)
        url = f"http://127.0.0.1:{port}/webui"
        if token:
            url = f"{url}?token={token}"
        return {
            "url": url,
            "token": token,
            "port": port,
            "configured": bool(token),
        }

    def start_telegram_polling(self) -> dict[str, object]:
        if not self.settings.telegram_bot_token:
            return {"status": "not_configured", "pid": None}
        status = self.status()
        current = status["telegram_polling"]
        if current["running"]:
            return {"status": "already_running", "pid": current["pid"]}
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
            external_pid = self._external_telegram_polling_pid()
            if external_pid:
                return {
                    "status": "externally_managed",
                    "pid": external_pid,
                    "managed_by": "external",
                }
            return {"status": "not_running", "pid": None}
        self._terminate_process(pid)
        state.pop("telegram_polling_pid", None)
        self._write_state(state)
        return {"status": "stopped", "pid": pid}

    def _telegram_polling_status(self, state: dict[str, object]) -> dict[str, object]:
        stored_pid = self._pid_value(state.get("telegram_polling_pid"))
        if stored_pid and self._process_exists(stored_pid):
            return {"running": True, "pid": stored_pid, "managed_by": "dashboard"}
        if stored_pid:
            state.pop("telegram_polling_pid", None)
            self._write_state(state)
        external_pid = self._external_telegram_polling_pid()
        if external_pid:
            return {"running": True, "pid": external_pid, "managed_by": "external"}
        return {"running": False, "pid": None, "managed_by": "none"}

    def _external_telegram_polling_pid(self) -> int | None:
        if os.name == "nt":
            return None
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == os.getpid():
                continue
            try:
                arguments = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            except (OSError, PermissionError):
                continue
            if self._is_telegram_poll_command([item for item in arguments if item]):
                return pid
        return None

    def _external_lifecycle_pid(self) -> int | None:
        if os.name == "nt":
            return None
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == os.getpid():
                continue
            try:
                arguments = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            except (OSError, PermissionError):
                continue
            values = [item for item in arguments if item]
            if self._is_lifecycle_command(values):
                return pid
        return None

    def _is_lifecycle_command(self, arguments: list[str]) -> bool:
        try:
            module_index = arguments.index("gugabobo.main")
        except ValueError:
            module_index = -1
        if module_index >= 0 and arguments[module_index + 1 : module_index + 2] == ["daemon"]:
            return True
        return bool(
            arguments
            and Path(arguments[0]).name in {"gugabobo", "gugabobo.exe"}
            and arguments[1:2] == ["daemon"]
        )

    def _is_telegram_poll_command(self, arguments: list[str]) -> bool:
        try:
            module_index = arguments.index("gugabobo.main")
        except ValueError:
            module_index = -1
        if module_index >= 0 and arguments[module_index + 1 : module_index + 3] == [
            "telegram",
            "poll",
        ]:
            return True
        return bool(
            arguments
            and Path(arguments[0]).name in {"gugabobo", "gugabobo.exe"}
            and arguments[1:3] == ["telegram", "poll"]
        )

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

    def _napcat_process_status(self) -> dict[str, object]:
        pids = self._napcat_pids()
        return {
            "running": bool(pids),
            "pids": pids,
            "dir": str(self.settings.napcat_dir),
            "webui": self.napcat_webui_url(),
        }

    def _napcat_pids(self) -> list[int]:
        if os.name != "nt":
            return []
        directory = str(self.settings.napcat_dir).replace("'", "''")
        script = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.ExecutablePath -like '{directory}*' }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
        )
        pids: list[int] = []
        for line in result.stdout.splitlines():
            pid = self._pid_value(line.strip())
            if pid and pid != os.getpid():
                pids.append(pid)
        return sorted(set(pids))

    def _napcat_webui_config(self) -> dict[str, object]:
        config_path = (
            self.settings.napcat_dir
            / "versions"
            / "9.9.26-44498"
            / "resources"
            / "app"
            / "napcat"
            / "config"
            / "webui.json"
        )
        if not config_path.exists():
            return {}
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _qq_reply_mode(self) -> str:
        if self.settings.napcat_reply_enabled:
            return "active"
        if self.settings.napcat_passive_reply_enabled:
            return "passive"
        return "off"

    def _tcp_status(self, host: str, port: int) -> dict[str, object]:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return {"running": True, "host": host, "port": port}
        except OSError as error:
            return {
                "running": False,
                "host": host,
                "port": port,
                "error": str(error),
            }

    def _url_tcp_status(self, url: str) -> dict[str, object]:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        if parsed.port:
            port = parsed.port
        elif parsed.scheme == "https":
            port = 443
        else:
            port = 80
        return self._tcp_status(host, port)

    def _qq_checks(
        self,
        webui: dict[str, object],
        napcat_api: dict[str, object],
        reply_mode: str,
    ) -> list[dict[str, object]]:
        return [
            {
                "name": "API",
                "ok": True,
                "detail": "gugabobo API is running",
            },
            {
                "name": "NapCat WebUI",
                "ok": bool(webui["running"]),
                "detail": "127.0.0.1:6099 should be reachable",
            },
            {
                "name": "NapCat OneBot API",
                "ok": bool(napcat_api["running"]) or reply_mode == "passive",
                "detail": "only required when active reply is enabled",
            },
            {
                "name": "QQ reply mode",
                "ok": reply_mode != "off",
                "detail": reply_mode,
            },
        ]
