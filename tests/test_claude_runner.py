import subprocess

from gugabobo.config import get_settings
from gugabobo.infra import claude_runner as runner_module
from gugabobo.infra.claude_runner import ClaudeCodeRunner


def test_configured_reflects_which(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setattr(runner_module.shutil, "which", lambda name: "/usr/bin/claude")
    assert ClaudeCodeRunner().configured is True

    monkeypatch.setattr(runner_module.shutil, "which", lambda name: None)
    assert ClaudeCodeRunner().configured is False
    get_settings.cache_clear()


def test_run_builds_headless_command(monkeypatch, tmp_path):
    get_settings.cache_clear()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)

    result = ClaudeCodeRunner().run("fix the bug", cwd=tmp_path)

    assert result.ok is True
    assert result.output == "done"
    assert captured["command"][0:4] == ["claude", "-p", "fix the bug", "--output-format"]
    assert "bypassPermissions" in captured["command"]
    assert captured["cwd"] == str(tmp_path)
    get_settings.cache_clear()


def test_run_reports_failure(monkeypatch, tmp_path):
    get_settings.cache_clear()

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)

    result = ClaudeCodeRunner().run("do it", cwd=tmp_path)

    assert result.ok is False
    assert result.error == "boom"
    get_settings.cache_clear()


def test_run_handles_timeout(monkeypatch, tmp_path):
    get_settings.cache_clear()

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)

    result = ClaudeCodeRunner().run("slow", cwd=tmp_path)

    assert result.ok is False
    assert "timed out" in result.error
    get_settings.cache_clear()
