from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings
from gugabobo.infra.container_runtime import ContainerRuntime


_PERMISSION_MODE = "acceptEdits"
_ALLOWED_TOOLS = "Read,Edit,Write,Glob,Grep"


@dataclass(frozen=True)
class RunResult:
    ok: bool
    output: str
    error: str = ""


class ClaudeCodeRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        container_runtime: ContainerRuntime | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.container_runtime = container_runtime or ContainerRuntime(self.settings)

    @property
    def configured(self) -> bool:
        return self.container_runtime.ready

    def run(self, prompt: str, cwd: Path) -> RunResult:
        if not self.configured:
            return RunResult(
                ok=False,
                output="",
                error="isolated runner is unavailable; build the configured container image",
            )
        command = [
            self.settings.claude_bin,
            "--print",
            "--input-format",
            "text",
            "--output-format",
            "json",
            "--permission-mode",
            _PERMISSION_MODE,
            "--allowedTools",
            _ALLOWED_TOOLS,
            "--disable-slash-commands",
            "--no-session-persistence",
            "--no-chrome",
            "--max-budget-usd",
            str(self.settings.claude_max_budget_usd),
        ]
        environment = {
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
        }
        if self.settings.claude_base_url:
            environment["ANTHROPIC_BASE_URL"] = self.settings.claude_base_url.rstrip("/")
        if self.settings.claude_auth_token:
            environment["ANTHROPIC_AUTH_TOKEN"] = self.settings.claude_auth_token
        result = self.container_runtime.run(
            workspace=cwd,
            command=command,
            network="bridge",
            timeout=self.settings.claude_timeout_seconds,
            input_text=prompt,
            home_dir=self.settings.runner_home_dir,
            environment=environment,
        )
        return RunResult(
            ok=result.returncode == 0,
            output=result.stdout,
            error=result.stderr,
        )
