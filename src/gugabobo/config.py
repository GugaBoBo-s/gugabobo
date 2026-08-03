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
    telegram_community_group_url: str = "https://t.me/ScarletKc_Group"
    telegram_companion_bot_url: str = "https://t.me/FogMoeBot"
    telegram_announcement_channel_url: str = "https://t.me/FOG_MOE"
    telegram_summary_bot_url: str = "https://t.me/rigerubot?startgroup=true"
    telegram_developer_gugabobo_url: str = "https://t.me/woshigugabobo"
    telegram_developer_scarletkc_url: str = "https://t.me/scarletkc"
    telegram_github_scarletkc_url: str = "https://github.com/scarletkc"
    telegram_github_fogmoe_url: str = "https://github.com/FogMoe"
    telegram_github_geyugong_url: str = "https://github.com/orgs/FogMoe/people/GeYugong"
    telegram_github_gugabobo_url: str = "https://github.com/GugaBoBo-s"
    github_token: str = Field(default="", repr=False)
    github_owner: str = "GugaBoBo-s"
    github_repo: str = "gugabobo"
    github_api_url: str = "https://api.github.com"
    github_review_enabled: bool = False
    github_organization: str = "GugaBoBo-s"
    github_review_interval_seconds: int = Field(default=300, ge=30)
    github_review_max_files: int = Field(default=3000, ge=1, le=3000)
    github_review_max_patch_chars: int = Field(default=120000, ge=1000, le=1000000)
    github_issue_enabled: bool = False
    github_issue_interval_seconds: int = Field(default=600, ge=30)
    github_issue_max_per_scan: int = Field(default=20, ge=1, le=500)
    github_issue_min_confidence: float = Field(default=0.75, ge=0, le=1)
    github_issue_auto_fix_enabled: bool = True
    github_issue_auto_fix_repositories: str = ""
    auto_deploy_enabled: bool = True
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
    code_claude_model: str = "claude-opus-4-8"
    codex_bin: str = "codex"
    code_openai_model: str = "gpt-5.6-sol"
    code_deepseek_model: str = "deepseek-v4-pro"
    code_deepseek_runner_model: str = "deepseek-v4-pro[1m]"
    code_model_timeout_seconds: int = Field(default=120, ge=1)
    claude_timeout_seconds: int = Field(default=900, ge=1)
    claude_max_budget_usd: float = Field(default=5.0, gt=0, le=100)
    sandbox_check_timeout_seconds: int = Field(default=300, ge=1)
    execution_lease_seconds: int = Field(default=120, ge=30, le=3600)
    execution_heartbeat_seconds: int = Field(default=15, ge=1, le=300)
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
    serper_api_key: str = Field(default="", repr=False)
    serper_base_url: str = "https://google.serper.dev"
    web_search_proxy: str = ""
    web_search_timeout_seconds: int = Field(default=20, ge=1)
    web_search_max_results: int = Field(default=6, ge=1, le=20)
    read_url_timeout_seconds: int = Field(default=20, ge=1)
    read_url_max_chars: int = Field(default=8000, ge=500, le=50000)
    mcd_mcp_enabled: bool = False
    mcd_mcp_url: str = "https://mcp.mcd.cn"
    mcd_mcp_token: str = Field(default="", repr=False)
    mcd_mcp_timeout_seconds: int = Field(default=30, ge=1)
    mcd_mcp_proxy: str = ""
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_context_messages: int = Field(default=400, ge=1)
    llm_memory_items: int = Field(default=12, ge=0)
    llm_history_token_budget: int = Field(default=24000, ge=1)
    llm_summary_trigger_tokens: int = Field(default=24000, ge=1)
    llm_summary_keep_recent_tokens: int = Field(default=8000, ge=0)
    vexor_memory_enabled: bool = False
    vexor_provider: str = "openai"
    vexor_model: str = "text-embedding-3-small"
    vexor_api_key: str = Field(default="", repr=False)
    vexor_base_url: str = "https://api.openai.com/v1"
    vexor_memory_candidates: int = Field(default=200, ge=1, le=2000)
    glitter_send_root: Path = Path(".gugabobo/glitter-send")
    glitter_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    remote_skill_timeout_seconds: int = Field(default=20, ge=1, le=120)
    remote_skill_max_chars: int = Field(default=50000, ge=1000, le=200000)
    prompt_guidance_dir: Path = Path(".")
    prompt_guidance_max_chars: int = Field(default=50000, ge=1000, le=200000)
    x_reader_timeout_seconds: int = Field(default=20, ge=1, le=120)
    x_reader_max_chars: int = Field(default=12000, ge=1000, le=50000)
    steam_timeout_seconds: int = Field(default=15, ge=1, le=120)
    steam_max_response_chars: int = Field(default=100000, ge=1000, le=1000000)
    steam_retry_count: int = Field(default=1, ge=0, le=3)
    steam_country_code: str = "CN"
    steam_language: str = "schinese"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.runner_home_dir.mkdir(parents=True, exist_ok=True)
        self.glitter_send_root.mkdir(parents=True, exist_ok=True)

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

    @property
    def github_issue_auto_fix_repository_set(self) -> set[str]:
        configured = {
            item.strip().casefold()
            for item in self.github_issue_auto_fix_repositories.split(",")
            if item.strip()
        }
        return configured or {f"{self.github_owner}/{self.github_repo}".casefold()}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
