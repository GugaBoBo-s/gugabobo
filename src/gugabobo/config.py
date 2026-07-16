from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUGABOBO_", env_file=".env", extra="ignore")

    env: str = "dev"
    data_dir: Path = Path(".gugabobo")
    db_path: Path = Path(".gugabobo/gugabobo.db")
    log_dir: Path = Path(".gugabobo/logs")
    config_file_path: Path = Path(".env")
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    admin_token: str = Field(default="change-me", repr=False)
    owner_qq_ids: str = ""
    owner_telegram_ids: str = ""
    napcat_dir: Path = Path("D:/0code/处理程序/NapCat.44498.Shell")
    napcat_api_url: str = "http://127.0.0.1:3000"
    napcat_access_token: str = Field(default="", repr=False)
    napcat_reply_enabled: bool = False
    napcat_passive_reply_enabled: bool = False
    qq_group_wake_words: str = "gugabobo,咕嘎BoBo"
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = Field(default="", repr=False)
    telegram_reply_enabled: bool = False
    telegram_group_wake_words: str = "gugabobo,咕嘎BoBo"
    telegram_proxy: str = ""
    github_token: str = Field(default="", repr=False)
    github_owner: str = "GugaBoBo-s"
    github_repo: str = "gugabobo"
    github_api_url: str = "https://api.github.com"
    git_author_name: str = "GuGabobo"
    git_author_email: str = "263493647+GuGabobo@users.noreply.github.com"
    sandbox_dir: Path = Path(".gugabobo/sandbox")
    runner_container_runtime: str = "docker"
    runner_container_image: str = "gugabobo-runner:local"
    runner_home_dir: Path = Path(".gugabobo/claude-home")
    runner_memory_limit: str = "2g"
    runner_cpu_limit: str = "2"
    runner_pids_limit: int = Field(default=256, ge=16)
    claude_bin: str = "claude"
    claude_base_url: str = ""
    claude_auth_token: str = Field(default="", repr=False)
    claude_timeout_seconds: int = Field(default=900, ge=1)
    claude_max_budget_usd: float = Field(default=5.0, gt=0, le=100)
    sandbox_check_timeout_seconds: int = Field(default=300, ge=1)
    llm_provider: str = "moonshot"
    moonshot_api_key: str = Field(default="", repr=False)
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    moonshot_model: str = "kimi-k2.6"
    deepseek_api_key: str = Field(default="", repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    openai_api_key: str = Field(default="", repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.6"
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_context_messages: int = Field(default=400, ge=1)
    llm_memory_items: int = Field(default=12, ge=0)
    llm_history_token_budget: int = Field(default=24000, ge=1)
    llm_summary_trigger_tokens: int = Field(default=24000, ge=1)
    llm_summary_keep_recent_tokens: int = Field(default=8000, ge=0)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.runner_home_dir.mkdir(parents=True, exist_ok=True)

    @property
    def owner_qq_id_set(self) -> set[str]:
        return {item.strip() for item in self.owner_qq_ids.split(",") if item.strip()}

    @property
    def owner_telegram_id_set(self) -> set[str]:
        return {item.strip() for item in self.owner_telegram_ids.split(",") if item.strip()}

    @property
    def qq_group_wake_word_list(self) -> list[str]:
        return [item.strip() for item in self.qq_group_wake_words.split(",") if item.strip()]

    @property
    def telegram_group_wake_word_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.telegram_group_wake_words.split(",")
            if item.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
