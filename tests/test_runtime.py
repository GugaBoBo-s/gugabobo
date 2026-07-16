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
