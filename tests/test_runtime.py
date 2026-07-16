from gugabobo.config import get_settings
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.infra.runtime import RuntimeManager


def test_status_detects_externally_managed_telegram(monkeypatch):
    manager = RuntimeManager()
    monkeypatch.setattr(ContainerRuntime, "configured", property(lambda _self: False))
    monkeypatch.setattr(manager, "_read_state", lambda: {})
    monkeypatch.setattr(manager, "_external_telegram_polling_pid", lambda: 4321)

    status = manager.status()["telegram_polling"]

    assert status["running"] is True
    assert status["pid"] == 4321
    assert status["managed_by"] == "external"


def test_dashboard_stop_does_not_kill_external_telegram(monkeypatch):
    manager = RuntimeManager()
    monkeypatch.setattr(manager, "_read_state", lambda: {})
    monkeypatch.setattr(manager, "_write_state", lambda _state: None)
    monkeypatch.setattr(manager, "_external_telegram_polling_pid", lambda: 4321)

    result = manager.stop_telegram_polling()

    assert result == {
        "status": "externally_managed",
        "pid": 4321,
        "managed_by": "external",
    }


def test_telegram_poll_command_detection():
    manager = RuntimeManager()

    assert manager._is_telegram_poll_command(
        ["python", "-m", "gugabobo.main", "telegram", "poll", "--send"]
    )
    assert manager._is_telegram_poll_command(["gugabobo", "telegram", "poll"])
    assert not manager._is_telegram_poll_command(["python", "-m", "gugabobo.main", "api"])


def test_lifecycle_command_detection():
    manager = RuntimeManager()

    assert manager._is_lifecycle_command(["python", "-m", "gugabobo.main", "daemon"])
    assert manager._is_lifecycle_command(["gugabobo", "daemon", "--interval", "30"])
    assert manager._is_lifecycle_command(
        ["/opt/gugabobo/repo/.venv/bin/python", "/opt/gugabobo/repo/.venv/bin/gugabobo", "daemon"]
    )
    assert not manager._is_lifecycle_command(["python", "-m", "gugabobo.main", "api"])


def test_status_reports_claude_gateway_without_exposing_token(monkeypatch):
    monkeypatch.setenv("GUGABOBO_CLAUDE_BASE_URL", "https://gateway.example.com")
    monkeypatch.setenv("GUGABOBO_CLAUDE_AUTH_TOKEN", "runner-secret")
    get_settings.cache_clear()
    manager = RuntimeManager()
    monkeypatch.setattr(ContainerRuntime, "configured", property(lambda _self: False))

    status = manager.status()["self_improvement"]

    assert status["claude_gateway_configured"] is True
    assert status["claude_base_url"] == "https://gateway.example.com"
    assert status["code_models"]["order"] == ["claude", "openai", "deepseek"]
    assert status["code_models"]["claude"]["configured"] is True
    assert "runner-secret" not in str(status)
    get_settings.cache_clear()


def test_status_reads_auto_deploy_state(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    (tmp_path / "deploy-status.json").write_text(
        '{"status":"deployed","current_revision":"abc","detail":"healthy"}',
        encoding="utf-8",
    )
    manager = RuntimeManager()
    monkeypatch.setattr(ContainerRuntime, "configured", property(lambda _self: False))

    status = manager.status()["auto_deploy"]

    assert status["status"] == "deployed"
    assert status["current_revision"] == "abc"
    assert status["detail"] == "healthy"
    get_settings.cache_clear()
