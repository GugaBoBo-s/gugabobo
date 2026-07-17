from typer.testing import CliRunner

from gugabobo.adapters.cli import app
from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger
from gugabobo.infra.runtime import build_agent


runner = CliRunner()


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
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


def test_memory_commands(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    add_result = runner.invoke(
        app,
        ["memory", "add", "用户喜欢蓝色", "--subject", "qq:user:1", "--memory-type", "preference"],
    )
    list_result = runner.invoke(app, ["memory", "list", "--subject", "qq:user:1"])

    assert add_result.exit_code == 0
    assert list_result.exit_code == 0
    assert "用户喜欢蓝色" in list_result.output
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_improvement_cli_flow(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    add_feedback = runner.invoke(app, ["feedback", "add", "回复太长"])
    create_result = runner.invoke(app, ["improve", "create", "1", "--scope", "chat"])
    list_result = runner.invoke(app, ["improve", "list"])
    approve_result = runner.invoke(app, ["improve", "approve", "1"])
    tasks_result = runner.invoke(app, ["tasks", "list"])

    assert add_feedback.exit_code == 0
    assert create_result.exit_code == 0
    assert "已创建改进任务 #1" in create_result.output
    assert list_result.exit_code == 0
    assert "pending" in list_result.output
    assert approve_result.exit_code == 0
    assert tasks_result.exit_code == 0
    assert "self_improvement" in tasks_result.output
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_improve_create_rejects_missing_feedback(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["improve", "create", "999"])

    assert result.exit_code != 0
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_execution_commands_cancel_and_retry_run(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "gugabobo.adapters.cli.ContainerRuntime.stop",
        lambda self, container_name: True,
    )
    store = build_agent().store
    task_id = store.add_task("Run control")
    improvement_id = store.add_improvement_task(task_id, approval_status="approved")
    claim = store.claim_improvement_run(improvement_id, "cli-worker", 120)
    assert claim is not None

    listed = runner.invoke(app, ["execution", "list"])
    cancelled = runner.invoke(app, ["execution", "cancel", "improvement", str(improvement_id)])
    store.finish_improvement_run(
        improvement_id,
        str(claim["lease_token"]),
        "cancelled",
        "cancelled",
    )
    retried = runner.invoke(app, ["execution", "retry", "improvement", str(improvement_id)])

    assert listed.exit_code == 0
    assert "improvement" in listed.output
    assert cancelled.exit_code == 0
    assert "cancel_requested" in cancelled.output
    assert retried.exit_code == 0
    assert "retry_requested" in retried.output
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_summary_commands(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    set_result = runner.invoke(
        app,
        ["summary", "set", "qq:user:1", "用户正在测试上下文。"],
    )
    show_result = runner.invoke(app, ["summary", "show", "qq:user:1"])

    assert set_result.exit_code == 0
    assert show_result.exit_code == 0
    assert "用户正在测试上下文" in show_result.output
    get_settings.cache_clear()
    get_logger.cache_clear()
