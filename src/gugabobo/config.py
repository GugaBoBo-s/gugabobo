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
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    admin_token: str = Field(default="change-me", repr=False)
    owner_qq_ids: str = ""
    napcat_api_url: str = "http://127.0.0.1:3000"
    napcat_access_token: str = Field(default="", repr=False)
    napcat_reply_enabled: bool = False
    napcat_passive_reply_enabled: bool = False
    qq_group_wake_words: str = "gugabobo,咕嘎啵啵"
    llm_provider: str = "moonshot"
    moonshot_api_key: str = Field(default="", repr=False)
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    moonshot_model: str = "kimi-k2.6"
    deepseek_api_key: str = Field(default="", repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    llm_timeout_seconds: int = 60
    llm_context_messages: int = 12

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def owner_qq_id_set(self) -> set[str]:
        return {item.strip() for item in self.owner_qq_ids.split(",") if item.strip()}

    @property
    def qq_group_wake_word_list(self) -> list[str]:
        return [item.strip() for item in self.qq_group_wake_words.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
