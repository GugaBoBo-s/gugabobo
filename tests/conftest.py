import pytest

from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger


@pytest.fixture(autouse=True)
def isolate_runtime_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime"
    values = {
        "GUGABOBO_ENV": "test",
        "GUGABOBO_DATA_DIR": str(data_dir),
        "GUGABOBO_DB_PATH": str(data_dir / "test.db"),
        "GUGABOBO_LOG_DIR": str(data_dir / "logs"),
        "GUGABOBO_CONFIG_FILE_PATH": str(tmp_path / ".env"),
        "GUGABOBO_ADMIN_TOKEN": "change-me",
        "GUGABOBO_OWNER_QQ_IDS": "",
        "GUGABOBO_OWNER_TELEGRAM_IDS": "",
        "GUGABOBO_NAPCAT_DIR": str(tmp_path / "napcat"),
        "GUGABOBO_NAPCAT_API_URL": "http://127.0.0.1:1",
        "GUGABOBO_NAPCAT_ACCESS_TOKEN": "",
        "GUGABOBO_NAPCAT_REPLY_ENABLED": "false",
        "GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED": "false",
        "GUGABOBO_TELEGRAM_BOT_TOKEN": "",
        "GUGABOBO_TELEGRAM_WEBHOOK_SECRET": "",
        "GUGABOBO_TELEGRAM_REPLY_ENABLED": "false",
        "GUGABOBO_TELEGRAM_PROXY": "",
        "GUGABOBO_GITHUB_TOKEN": "",
        "GUGABOBO_GITHUB_REVIEW_ENABLED": "false",
        "GUGABOBO_GITHUB_ISSUE_ENABLED": "false",
        "GUGABOBO_SANDBOX_DIR": str(data_dir / "sandbox"),
        "GUGABOBO_RUNNER_HOME_DIR": str(data_dir / "claude-home"),
        "GUGABOBO_CLAUDE_BASE_URL": "",
        "GUGABOBO_CLAUDE_AUTH_TOKEN": "",
        "GUGABOBO_LLM_PROVIDER": "moonshot",
        "GUGABOBO_MOONSHOT_API_KEY": "",
        "GUGABOBO_DEEPSEEK_API_KEY": "",
        "GUGABOBO_OPENAI_API_KEY": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    get_logger.cache_clear()
    yield
    get_settings.cache_clear()
    get_logger.cache_clear()
