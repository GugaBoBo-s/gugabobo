from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gugabobo.config import Settings, get_settings
from gugabobo.infra.redaction import redact_sensitive


_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True)
class ContainerResult:
    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False


class ContainerMonitor(Protocol):
    @property
    def container_name(self) -> str: ...

    def pulse(self) -> bool: ...


class ContainerRuntime:
    def __init__(
        self,
        settings: Settings | None = None,
        monitor: ContainerMonitor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.monitor = monitor

    @property
    def configured(self) -> bool:
        return shutil.which(self.settings.runner_container_runtime) is not None

    @property
    def image_available(self) -> bool:
        if not self.configured:
            return False
        result = subprocess.run(
            [
                self.settings.runner_container_runtime,
                "image",
                "inspect",
                self.settings.runner_container_image,
            ],
            capture_output=True,
            text=True,
            check=False,
            env=self._host_env(),
        )
        return result.returncode == 0

    @property
    def ready(self) -> bool:
        return self.configured and self.image_available

    def run(
        self,
        workspace: Path,
        command: list[str],
        network: str,
        timeout: int,
        input_text: str | None = None,
        home_dir: Path | None = None,
        environment: dict[str, str] | None = None,
        host_gateway: bool = False,
    ) -> ContainerResult:
        resolved_workspace = workspace.resolve()
        resolved_home = home_dir.resolve() if home_dir else None
        docker_command = [
            self.settings.runner_container_runtime,
            "run",
            "--rm",
            "--init",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--network={network}",
            f"--pids-limit={self.settings.runner_pids_limit}",
            f"--memory={self.settings.runner_memory_limit}",
            f"--cpus={self.settings.runner_cpu_limit}",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--mount",
            self._mount(resolved_workspace, "/workspace"),
            "--workdir",
            "/workspace",
            "--env",
            "NO_COLOR=1",
            "--env",
            "PYTHONUNBUFFERED=1",
        ]
        if input_text is not None:
            docker_command.append("--interactive")
        if host_gateway:
            docker_command.extend(["--add-host", "host.docker.internal:host-gateway"])
        if resolved_home:
            resolved_home.mkdir(parents=True, exist_ok=True)
            docker_command.extend(
                [
                    "--mount",
                    self._mount(resolved_home, "/home/runner"),
                    "--env",
                    "HOME=/home/runner",
                ]
            )
        else:
            docker_command.extend(["--env", "HOME=/tmp"])
        if self.monitor is not None:
            docker_command.extend(["--name", self.monitor.container_name])
        process_environment = self._host_env()
        for name, value in sorted((environment or {}).items()):
            if not _ENVIRONMENT_NAME.fullmatch(name):
                raise ValueError(f"invalid container environment name: {name}")
            docker_command.extend(["--env", name])
            process_environment[name] = value
        docker_command.extend([self.settings.runner_container_image, *command])
        if self.monitor is not None:
            return self._run_monitored(
                docker_command,
                process_environment,
                timeout,
                input_text,
            )
        try:
            result = subprocess.run(
                docker_command,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=process_environment,
            )
        except subprocess.TimeoutExpired:
            return ContainerResult(returncode=124, stdout="", stderr="container run timed out")
        secrets = self._known_secrets()
        return ContainerResult(
            returncode=result.returncode,
            stdout=redact_sensitive(result.stdout, secrets),
            stderr=redact_sensitive(result.stderr, secrets),
        )

    def _run_monitored(
        self,
        command: list[str],
        environment: dict[str, str],
        timeout: int,
        input_text: str | None,
    ) -> ContainerResult:
        if self.monitor is None or not self.monitor.pulse():
            return ContainerResult(125, "", "container run cancelled", cancelled=True)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        deadline = time.monotonic() + timeout
        pending_input = input_text
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.stop(self.monitor.container_name)
                stdout, stderr = self._finish_process(process)
                return self._result(124, stdout, stderr or "container run timed out")
            try:
                stdout, stderr = process.communicate(
                    input=pending_input,
                    timeout=min(1.0, remaining),
                )
                return self._result(process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                pending_input = None
                if self.monitor.pulse():
                    continue
                self.stop(self.monitor.container_name)
                stdout, stderr = self._finish_process(process)
                message = stderr or "container run cancelled"
                result = self._result(125, stdout, message)
                return ContainerResult(
                    result.returncode,
                    result.stdout,
                    result.stderr,
                    cancelled=True,
                )

    def stop(self, container_name: str) -> bool:
        if not re.fullmatch(r"gugabobo-[a-z0-9-]+", container_name):
            return False
        if not self.configured:
            return False
        try:
            result = subprocess.run(
                [
                    self.settings.runner_container_runtime,
                    "stop",
                    "--time",
                    "1",
                    container_name,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                env=self._host_env(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _finish_process(self, process: subprocess.Popen[str]) -> tuple[str, str]:
        try:
            return process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate()

    def _result(self, returncode: int, stdout: str, stderr: str) -> ContainerResult:
        secrets = self._known_secrets()
        return ContainerResult(
            returncode=returncode,
            stdout=redact_sensitive(stdout, secrets),
            stderr=redact_sensitive(stderr, secrets),
        )

    def _mount(self, source: Path, target: str) -> str:
        source_text = str(source)
        if "," in source_text:
            raise ValueError("container mount paths cannot contain commas")
        return f"type=bind,source={source_text},target={target}"

    def _host_env(self) -> dict[str, str]:
        blocked_names = {
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "TELEGRAM_BOT_TOKEN",
        }
        return {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GUGABOBO_") and key not in blocked_names
        }

    def _known_secrets(self) -> tuple[str, ...]:
        return (
            self.settings.admin_token,
            self.settings.github_token,
            self.settings.telegram_bot_token,
            self.settings.telegram_webhook_secret,
            self.settings.napcat_access_token,
            self.settings.moonshot_api_key,
            self.settings.deepseek_api_key,
            self.settings.openai_api_key,
            self.settings.claude_auth_token,
        )
