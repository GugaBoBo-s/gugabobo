from gugabobo.config import get_settings
from gugabobo.infra.claude_runner import ClaudeCodeRunner
from gugabobo.infra.container_runtime import ContainerResult


class FakeContainerRuntime:
    def __init__(self, ready=True, result=None):
        self.ready = ready
        self.result = result or ContainerResult(returncode=0, stdout="done", stderr="")
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_configured_requires_isolated_runtime():
    get_settings.cache_clear()
    assert ClaudeCodeRunner(
        container_runtime=FakeContainerRuntime(), auth_token="token"
    ).configured is True
    assert ClaudeCodeRunner(container_runtime=FakeContainerRuntime()).configured is False
    assert ClaudeCodeRunner(
        container_runtime=FakeContainerRuntime(ready=False), auth_token="token"
    ).configured is False
    get_settings.cache_clear()


def test_run_builds_isolated_headless_command(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_CLAUDE_PERMISSION_MODE", "bypassPermissions")
    monkeypatch.setenv("GUGABOBO_CLAUDE_ALLOWED_TOOLS", "Bash,Read,Write")
    monkeypatch.setenv("GUGABOBO_CLAUDE_BASE_URL", "https://gateway.example.com/")
    monkeypatch.setenv("GUGABOBO_CLAUDE_AUTH_TOKEN", "runner-secret")
    get_settings.cache_clear()
    runtime = FakeContainerRuntime()

    result = ClaudeCodeRunner(container_runtime=runtime).run("fix the bug", cwd=tmp_path)

    assert result.ok is True
    assert result.output == "done"
    call = runtime.calls[0]
    assert call["workspace"] == tmp_path
    assert call["network"] == "bridge"
    assert call["input_text"] == "fix the bug"
    assert "fix the bug" not in call["command"]
    assert "acceptEdits" in call["command"]
    assert "bypassPermissions" not in call["command"]
    assert "Bash,Read,Write" not in call["command"]
    assert "--no-session-persistence" in call["command"]
    assert "--bare" in call["command"]
    assert "--safe-mode" in call["command"]
    assert "--strict-mcp-config" in call["command"]
    assert call["host_gateway"] is True
    assert "home_dir" not in call
    assert call["environment"]["ANTHROPIC_AUTH_TOKEN"] != "runner-secret"
    assert call["environment"]["ANTHROPIC_API_KEY"] != "runner-secret"
    assert call["environment"]["ANTHROPIC_BASE_URL"].startswith(
        "http://host.docker.internal:"
    )
    get_settings.cache_clear()


def test_run_reports_container_failure(tmp_path):
    get_settings.cache_clear()
    runtime = FakeContainerRuntime(
        result=ContainerResult(returncode=1, stdout="", stderr="boom")
    )

    result = ClaudeCodeRunner(container_runtime=runtime, auth_token="token").run(
        "do it", cwd=tmp_path
    )

    assert result.ok is False
    assert result.error == "boom"
    get_settings.cache_clear()


def test_run_fails_closed_when_runtime_is_missing(tmp_path):
    get_settings.cache_clear()
    runtime = FakeContainerRuntime(ready=False)

    result = ClaudeCodeRunner(container_runtime=runtime).run("do it", cwd=tmp_path)

    assert result.ok is False
    assert "isolated runner" in result.error
    assert runtime.calls == []
    get_settings.cache_clear()
