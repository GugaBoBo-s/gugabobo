import subprocess

from gugabobo.config import get_settings
from gugabobo.infra import container_runtime as runtime_module
from gugabobo.infra.container_runtime import ContainerRuntime


def test_container_run_applies_isolation_and_strips_business_secrets(tmp_path, monkeypatch):
    github_token = "ghp_" + "a" * 26
    monkeypatch.setenv("GUGABOBO_GITHUB_TOKEN", github_token)
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
    )

    command = captured["command"]
    assert result.returncode == 0
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--network=bridge" in command
    assert "/var/run/docker.sock" not in " ".join(command)
    assert "GUGABOBO_GITHUB_TOKEN" not in captured["env"]
    assert "GITHUB_TOKEN" not in captured["env"]
    assert github_token not in " ".join(command)
    assert captured["input"] == "prompt"
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
