from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gugabobo.config import Settings, get_settings
from gugabobo.infra.claude_runner import ClaudeCodeRunner, RunResult
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.infra.credential_relay import CredentialRelay


class CodeRunner(Protocol):
    @property
    def configured(self) -> bool: ...

    def run(self, prompt: str, cwd: Path) -> RunResult: ...


class CodexCodeRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        container_runtime: ContainerRuntime | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.container_runtime = container_runtime or ContainerRuntime(self.settings)

    @property
    def configured(self) -> bool:
        return self.container_runtime.ready and bool(self.settings.openai_api_key)

    def run(self, prompt: str, cwd: Path) -> RunResult:
        if not self.configured:
            return RunResult(
                ok=False,
                output="",
                error="OpenAI code runner is not configured",
                provider="openai",
                model=self.settings.code_openai_model,
            )
        command = [
            self.settings.codex_bin,
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--strict-config",
            "--sandbox",
            "workspace-write",
            "--config",
            'shell_environment_policy.inherit="none"',
            "--config",
            "sandbox_workspace_write.network_access=false",
            "--model",
            self.settings.code_openai_model,
            "-",
        ]
        with CredentialRelay(
            self.settings.openai_base_url,
            self.settings.openai_api_key,
            auth_mode="bearer",
            timeout=self.settings.claude_timeout_seconds,
        ) as relay:
            result = self.container_runtime.run(
                workspace=cwd,
                command=command,
                network="bridge",
                timeout=self.settings.claude_timeout_seconds,
                input_text=prompt,
                environment={
                    "OPENAI_API_KEY": relay.relay_token,
                    "OPENAI_BASE_URL": relay.container_base_url,
                },
                host_gateway=True,
            )
        return RunResult(
            ok=result.returncode == 0,
            output=result.stdout,
            error=result.stderr,
            timed_out=result.returncode == 124,
            provider="openai",
            model=self.settings.code_openai_model,
        )


class CodeRunnerChain:
    def __init__(self, runners: list[CodeRunner]) -> None:
        if not runners:
            raise ValueError("at least one code runner is required")
        self.runners = runners

    @property
    def configured(self) -> bool:
        return self.runners[0].configured

    def run(self, prompt: str, cwd: Path) -> RunResult:
        for index, runner in enumerate(self.runners):
            if not runner.configured:
                return runner.run(prompt, cwd)
            result = runner.run(prompt, cwd)
            if result.ok or not result.timed_out or index == len(self.runners) - 1:
                return result
        return RunResult(ok=False, output="", error="code runner chain produced no result")


def build_code_runner(settings: Settings | None = None) -> CodeRunnerChain:
    resolved = settings or get_settings()
    runtime = ContainerRuntime(resolved)
    deepseek_base = resolved.deepseek_base_url.rstrip("/")
    if not deepseek_base.endswith("/anthropic"):
        deepseek_base = f"{deepseek_base}/anthropic"
    return CodeRunnerChain(
        [
            ClaudeCodeRunner(resolved, runtime),
            CodexCodeRunner(resolved, runtime),
            ClaudeCodeRunner(
                resolved,
                runtime,
                provider_name="deepseek",
                model=resolved.code_deepseek_runner_model,
                base_url=deepseek_base,
                auth_token=resolved.deepseek_api_key,
                require_token=True,
            ),
        ]
    )
