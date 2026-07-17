from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from gugabobo.config import Settings, get_settings
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.infra.credential_relay import CredentialRelay


_PERMISSION_MODE = "acceptEdits"
_ALLOWED_TOOLS = "Read,Edit,Write,Glob,Grep"
_RUNNER_SETTINGS = json.dumps(
    {
        "permissions": {
            "deny": [
                "Read(./.env)",
                "Read(./.env.*)",
                "Read(./.git/**)",
                "Read(//dev/**)",
                "Read(//etc/**)",
                "Read(//home/**)",
                "Read(//proc/**)",
                "Read(//run/**)",
                "Read(//sys/**)",
            ]
        }
    },
    separators=(",", ":"),
)


@dataclass(frozen=True)
class RunResult:
    ok: bool
    output: str
    error: str = ""
    timed_out: bool = False
    provider: str = ""
    model: str = ""


class ClaudeCodeRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        container_runtime: ContainerRuntime | None = None,
        provider_name: str = "claude",
        model: str | None = None,
        base_url: str | None = None,
        auth_token: str | None = None,
        require_token: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.container_runtime = container_runtime or ContainerRuntime(self.settings)
        self.provider_name = provider_name
        self.model = model or self.settings.code_claude_model
        self.base_url = self.settings.claude_base_url if base_url is None else base_url
        self.auth_token = self.settings.claude_auth_token if auth_token is None else auth_token
        self.require_token = require_token

    @property
    def configured(self) -> bool:
        return self.container_runtime.ready and bool(self.auth_token)

    def run(self, prompt: str, cwd: Path) -> RunResult:
        if not self.configured:
            return RunResult(
                ok=False,
                output="",
                error="isolated runner is unavailable; build the configured container image",
            )
        command = [
            self.settings.claude_bin,
            "--bare",
            "--safe-mode",
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
            "--strict-mcp-config",
            "--mcp-config",
            "{}",
            "--settings",
            _RUNNER_SETTINGS,
            "--max-budget-usd",
            str(self.settings.claude_max_budget_usd),
            "--model",
            self.model,
        ]
        upstream = self.base_url or "https://api.anthropic.com"
        auth_mode = "api_key" if urlsplit(upstream).hostname == "api.anthropic.com" else "bearer"
        with CredentialRelay(
            upstream,
            self.auth_token,
            auth_mode=auth_mode,
            timeout=self.settings.claude_timeout_seconds,
        ) as relay:
            result = self.container_runtime.run(
                workspace=cwd,
                command=command,
                network="bridge",
                timeout=self.settings.claude_timeout_seconds,
                input_text=prompt,
                environment={
                    "ANTHROPIC_API_KEY": relay.relay_token,
                    "ANTHROPIC_AUTH_TOKEN": relay.relay_token,
                    "ANTHROPIC_BASE_URL": relay.container_base_url,
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_AUTOUPDATER": "1",
                },
                host_gateway=True,
            )
        return RunResult(
            ok=result.returncode == 0,
            output=result.stdout,
            error=result.stderr,
            timed_out=result.returncode == 124,
            provider=self.provider_name,
            model=self.model,
        )
