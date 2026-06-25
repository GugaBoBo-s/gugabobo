from typer.testing import CliRunner

from gugabobo.adapters.cli import app
from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger


runner = CliRunner()


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_config_show_hides_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_ADMIN_TOKEN", "secret-token")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "admin_token: ***" in result.output
    assert "secret-token" not in result.output
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_messages_list_command(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    chat_result = runner.invoke(app, ["chat", "你好"])
    list_result = runner.invoke(app, ["messages", "list"])

    assert chat_result.exit_code == 0
    assert list_result.exit_code == 0
    assert "你好" in list_result.output
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_feedback_resolve_and_reopen_commands(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    add_result = runner.invoke(app, ["feedback", "add", "回复太长"])
    resolve_result = runner.invoke(app, ["feedback", "resolve", "1"])
    reopen_result = runner.invoke(app, ["feedback", "reopen", "1"])
    list_result = runner.invoke(app, ["feedback", "list"])

    assert add_result.exit_code == 0
    assert resolve_result.exit_code == 0
    assert reopen_result.exit_code == 0
    assert "#1 [new]" in list_result.output
    get_settings.cache_clear()
    get_logger.cache_clear()
