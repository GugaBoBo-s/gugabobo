import subprocess

from gugabobo.config import get_settings
from gugabobo.infra import container_runtime as runtime_module
from gugabobo.infra.container_runtime import ContainerRuntime


class FakeMonitor:
    container_name = "gugabobo-improvement-7-abcd1234"

    def __init__(self) -> None:
        self.pulses = 0

    def pulse(self) -> bool:
        self.pulses += 1
        return self.pulses == 1


class FakeProcess:
    returncode = 137

    def __init__(self) -> None:
        self.communications = 0

    def communicate(self, input=None, timeout=None):
        self.communications += 1
        if self.communications == 1:
            raise subprocess.TimeoutExpired("docker", timeout)
        return "partial output", ""

    def kill(self) -> None:
        self.returncode = -9


def test_container_run_applies_isolation_and_strips_business_secrets(tmp_path, monkeypatch):
    github_token = "ghp_" + "a" * 26
    claude_token = "sk-relay-" + "b" * 24
    monkeypatch.setenv("GUGABOBO_GITHUB_TOKEN", github_token)
    monkeypatch.setenv("GUGABOBO_CLAUDE_AUTH_TOKEN", claude_token)
    monkeypatch.setenv("GITHUB_TOKEN", "host-secret")
    get_settings.cache_clear()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        captured["input"] = kwargs["input"]
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(runtime_module.subprocess, "run", fake_run)
    workspace = tmp_path / "workspace"
    home = tmp_path / "runner-home"
    workspace.mkdir()

    result = ContainerRuntime().run(
        workspace=workspace,
        command=["claude", "--version"],
        network="bridge",
        timeout=30,
        input_text="prompt",
        home_dir=home,
        environment={
            "ANTHROPIC_AUTH_TOKEN": claude_token,
            "ANTHROPIC_BASE_URL": "https://gateway.example.com",
        },
        host_gateway=True,
    )

    command = captured["command"]
    assert result.returncode == 0
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--network=bridge" in command
    assert "host.docker.internal:host-gateway" in command
    assert "/var/run/docker.sock" not in " ".join(command)
    assert "GUGABOBO_GITHUB_TOKEN" not in captured["env"]
    assert "GITHUB_TOKEN" not in captured["env"]
    assert github_token not in " ".join(command)
    assert claude_token not in " ".join(command)
    assert "ANTHROPIC_AUTH_TOKEN" in command
    assert "ANTHROPIC_BASE_URL" in command
    assert captured["env"]["ANTHROPIC_AUTH_TOKEN"] == claude_token
    assert captured["env"]["ANTHROPIC_BASE_URL"] == "https://gateway.example.com"
    assert captured["input"] == "prompt"
    get_settings.cache_clear()


def test_container_run_rejects_invalid_environment_name(tmp_path):
    get_settings.cache_clear()

    try:
        ContainerRuntime().run(
            workspace=tmp_path,
            command=["true"],
            network="none",
            timeout=30,
            environment={"INVALID-NAME": "value"},
        )
    except ValueError as error:
        assert "invalid container environment name" in str(error)
    else:
        raise AssertionError("invalid environment name was accepted")
    finally:
        get_settings.cache_clear()


def test_container_output_is_redacted(tmp_path, monkeypatch):
    token = "1234567890:" + "AA" + "a" * 32
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", token)
    get_settings.cache_clear()

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout=token, stderr=token)

    monkeypatch.setattr(runtime_module.subprocess, "run", fake_run)
    result = ContainerRuntime().run(
        workspace=tmp_path,
        command=["false"],
        network="none",
        timeout=30,
    )

    assert token not in result.stdout
    assert token not in result.stderr
    assert result.stdout == "<redacted>"
    get_settings.cache_clear()


def test_monitored_container_is_named_and_stopped_after_cancellation(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monitor = FakeMonitor()
    captured = {}
    stop_commands = []

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return FakeProcess()

    def fake_run(command, **kwargs):
        stop_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="stopped", stderr="")

    monkeypatch.setattr(runtime_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runtime_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runtime_module.shutil, "which", lambda command: command)

    result = ContainerRuntime(monitor=monitor).run(
        workspace=tmp_path,
        command=["python", "-V"],
        network="none",
        timeout=30,
    )

    assert result.cancelled is True
    assert result.returncode == 125
    assert "--name" in captured["command"]
    assert monitor.container_name in captured["command"]
    assert any(command[:2] == ["docker", "stop"] for command in stop_commands)
    get_settings.cache_clear()
