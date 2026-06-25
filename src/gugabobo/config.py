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

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
