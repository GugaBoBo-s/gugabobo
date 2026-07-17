from gugabobo.infra.claude_runner import RunResult
from gugabobo.config import Settings
from gugabobo.infra.code_runner import CodeRunnerChain, CodexCodeRunner
from gugabobo.infra.container_runtime import ContainerResult


class FakeRunner:
    configured = True

    def __init__(self, result: RunResult) -> None:
        self.result = result
        self.calls = 0

    def run(self, prompt, cwd):
        self.calls += 1
        return self.result


class FakeContainerRuntime:
    ready = True

    def __init__(self) -> None:
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return ContainerResult(returncode=0, stdout="done", stderr="")


def test_code_runner_falls_back_after_two_timeouts(tmp_path):
    claude = FakeRunner(RunResult(False, "", "slow", True, "claude", "c"))
    openai = FakeRunner(RunResult(False, "", "slow", True, "openai", "g"))
    deepseek = FakeRunner(RunResult(True, "done", provider="deepseek", model="d"))

    result = CodeRunnerChain([claude, openai, deepseek]).run("fix", tmp_path)

    assert result.ok is True
    assert result.provider == "deepseek"
    assert [claude.calls, openai.calls, deepseek.calls] == [1, 1, 1]


def test_code_runner_stops_on_non_timeout_failure(tmp_path):
    claude = FakeRunner(RunResult(False, "", "auth failed", False, "claude", "c"))
    openai = FakeRunner(RunResult(True, "done", provider="openai", model="g"))

    result = CodeRunnerChain([claude, openai]).run("fix", tmp_path)

    assert result.error == "auth failed"
    assert openai.calls == 0


def test_codex_runner_uses_ephemeral_relay_and_workspace_sandbox(tmp_path) -> None:
    runtime = FakeContainerRuntime()
    settings = Settings(
        openai_api_key="upstream-secret",
        openai_base_url="https://gateway.example.com/v1",
    )

    result = CodexCodeRunner(settings, runtime).run("fix", tmp_path)

    assert result.ok is True
    call = runtime.calls[0]
    assert "--dangerously-bypass-approvals-and-sandbox" not in call["command"]
    assert "workspace-write" in call["command"]
    assert 'shell_environment_policy.inherit="none"' in call["command"]
    assert "sandbox_workspace_write.network_access=false" in call["command"]
    assert call["environment"]["OPENAI_API_KEY"] != "upstream-secret"
    assert call["environment"]["OPENAI_BASE_URL"].startswith(
        "http://host.docker.internal:"
    )
    assert call["host_gateway"] is True
