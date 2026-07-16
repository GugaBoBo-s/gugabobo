from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings
from gugabobo.infra.redaction import redact_sensitive


@dataclass(frozen=True)
class ContainerResult:
    returncode: int
    stdout: str
    stderr: str


class ContainerRuntime:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

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
        docker_command.extend([self.settings.runner_container_image, *command])
        try:
            result = subprocess.run(
                docker_command,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=self._host_env(),
            )
        except subprocess.TimeoutExpired:
            return ContainerResult(returncode=124, stdout="", stderr="container run timed out")
        secrets = self._known_secrets()
        return ContainerResult(
            returncode=result.returncode,
            stdout=redact_sensitive(result.stdout, secrets),
            stderr=redact_sensitive(result.stderr, secrets),
        )

    def _mount(self, source: Path, target: str) -> str:
        source_text = str(source)
        if "," in source_text:
            raise ValueError("container mount paths cannot contain commas")
        return f"type=bind,source={source_text},target={target}"

    def _host_env(self) -> dict[str, str]:
        blocked_names = {
            "ANTHROPIC_API_KEY",
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
        )
