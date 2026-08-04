from pathlib import Path

from pydantic import ValidationError

from gugabobo.config import Settings


EDITABLE_CONFIG_KEYS = {
    "GUGABOBO_OWNER_QQ_IDS",
    "GUGABOBO_OWNER_TELEGRAM_IDS",
    "GUGABOBO_NAPCAT_DIR",
    "GUGABOBO_NAPCAT_API_URL",
    "GUGABOBO_NAPCAT_REPLY_ENABLED",
    "GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED",
    "GUGABOBO_QQ_GROUP_WAKE_WORDS",
    "GUGABOBO_TELEGRAM_BOT_USERNAME",
    "GUGABOBO_TELEGRAM_REPLY_ENABLED",
    "GUGABOBO_TELEGRAM_GROUP_WAKE_WORDS",
    "GUGABOBO_TELEGRAM_PROXY",
    "GUGABOBO_TELEGRAM_COMMUNITY_GROUP_URL",
    "GUGABOBO_TELEGRAM_COMPANION_BOT_URL",
    "GUGABOBO_TELEGRAM_ANNOUNCEMENT_CHANNEL_URL",
    "GUGABOBO_TELEGRAM_SUMMARY_BOT_URL",
    "GUGABOBO_TELEGRAM_DEVELOPER_GUGABOBO_URL",
    "GUGABOBO_TELEGRAM_DEVELOPER_SCARLETKC_URL",
    "GUGABOBO_TELEGRAM_GITHUB_SCARLETKC_URL",
    "GUGABOBO_TELEGRAM_GITHUB_FOGMOE_URL",
    "GUGABOBO_TELEGRAM_GITHUB_GEYUGONG_URL",
    "GUGABOBO_TELEGRAM_GITHUB_GUGABOBO_URL",
    "GUGABOBO_GITHUB_OWNER",
    "GUGABOBO_GITHUB_REPO",
    "GUGABOBO_GITHUB_API_URL",
    "GUGABOBO_GITHUB_REVIEW_ENABLED",
    "GUGABOBO_GITHUB_ORGANIZATION",
    "GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS",
    "GUGABOBO_GITHUB_REVIEW_MAX_FILES",
    "GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS",
    "GUGABOBO_GITHUB_ISSUE_ENABLED",
    "GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS",
    "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN",
    "GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE",
    "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED",
    "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_REPOSITORIES",
    "GUGABOBO_AUTO_DEPLOY_ENABLED",
    "GUGABOBO_LLM_PROVIDER",
    "GUGABOBO_MOONSHOT_BASE_URL",
    "GUGABOBO_MOONSHOT_MODEL",
    "GUGABOBO_DEEPSEEK_BASE_URL",
    "GUGABOBO_DEEPSEEK_MODEL",
    "GUGABOBO_OPENAI_BASE_URL",
    "GUGABOBO_OPENAI_MODEL",
    "GUGABOBO_LLM_TIMEOUT_SECONDS",
    "GUGABOBO_LLM_CONTEXT_MESSAGES",
    "GUGABOBO_LLM_MEMORY_ITEMS",
    "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET",
    "GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS",
    "GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS",
    "GUGABOBO_RUNNER_CONTAINER_RUNTIME",
    "GUGABOBO_RUNNER_CONTAINER_IMAGE",
    "GUGABOBO_CLAUDE_BASE_URL",
    "GUGABOBO_CODE_CLAUDE_MODEL",
    "GUGABOBO_CODE_OPENAI_MODEL",
    "GUGABOBO_CODE_DEEPSEEK_MODEL",
    "GUGABOBO_CODE_DEEPSEEK_RUNNER_MODEL",
    "GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS",
}

BOOLEAN_CONFIG_KEYS = {
    "GUGABOBO_NAPCAT_REPLY_ENABLED",
    "GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED",
    "GUGABOBO_TELEGRAM_REPLY_ENABLED",
    "GUGABOBO_GITHUB_REVIEW_ENABLED",
    "GUGABOBO_GITHUB_ISSUE_ENABLED",
    "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED",
    "GUGABOBO_AUTO_DEPLOY_ENABLED",
}

INTEGER_CONFIG_KEYS = {
    "GUGABOBO_LLM_TIMEOUT_SECONDS",
    "GUGABOBO_LLM_CONTEXT_MESSAGES",
    "GUGABOBO_LLM_MEMORY_ITEMS",
    "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET",
    "GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS",
    "GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS",
    "GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS",
    "GUGABOBO_GITHUB_REVIEW_MAX_FILES",
    "GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS",
    "GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS",
    "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN",
    "GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS",
}

INTEGER_CONFIG_MINIMUMS = {
    "GUGABOBO_LLM_TIMEOUT_SECONDS": 1,
    "GUGABOBO_LLM_CONTEXT_MESSAGES": 1,
    "GUGABOBO_LLM_MEMORY_ITEMS": 0,
    "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET": 1,
    "GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS": 1,
    "GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS": 0,
    "GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS": 30,
    "GUGABOBO_GITHUB_REVIEW_MAX_FILES": 1,
    "GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS": 1000,
    "GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS": 30,
    "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN": 1,
    "GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS": 1,
}

INTEGER_CONFIG_MAXIMUMS = {
    "GUGABOBO_GITHUB_REVIEW_MAX_FILES": 3000,
    "GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS": 1000000,
    "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN": 500,
}

FLOAT_CONFIG_RANGES = {
    "GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE": (0.0, 1.0),
}

LLM_PROVIDERS = {"moonshot", "deepseek", "openai"}


class EnvFile:
    def __init__(self, path: Path = Path(".env")) -> None:
        self.path = path

    def update(self, values: dict[str, object]) -> dict[str, str]:
        normalized = self._normalize(values)
        lines = self._read_lines()
        seen: set[str] = set()
        updated_lines: list[str] = []
        for line in lines:
            key = self._line_key(line)
            if key in normalized:
                updated_lines.append(f"{key}={normalized[key]}")
                seen.add(key)
                continue
            updated_lines.append(line)
        for key, value in normalized.items():
            if key not in seen:
                updated_lines.append(f"{key}={value}")
        content = "\n".join(updated_lines).rstrip() + "\n"
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(self.path)
        return normalized

    def _read_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8").splitlines()

    def _line_key(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            return None
        key, _ = stripped.split("=", 1)
        return key.strip()

    def _normalize(self, values: dict[str, object]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in values.items():
            if key not in EDITABLE_CONFIG_KEYS:
                continue
            if key in BOOLEAN_CONFIG_KEYS:
                normalized[key] = self._bool_string(value)
                continue
            if key in INTEGER_CONFIG_KEYS:
                number = max(INTEGER_CONFIG_MINIMUMS[key], int(value))
                if key in INTEGER_CONFIG_MAXIMUMS:
                    number = min(INTEGER_CONFIG_MAXIMUMS[key], number)
                normalized[key] = str(number)
                continue
            if key in FLOAT_CONFIG_RANGES:
                minimum, maximum = FLOAT_CONFIG_RANGES[key]
                normalized[key] = str(min(maximum, max(minimum, float(value))))
                continue
            normalized[key] = str(value).replace("\r", "").replace("\n", "").strip()
        provider = normalized.get("GUGABOBO_LLM_PROVIDER")
        if provider is not None and provider not in LLM_PROVIDERS:
            allowed = ", ".join(sorted(LLM_PROVIDERS))
            raise ValueError(f"GUGABOBO_LLM_PROVIDER must be one of: {allowed}")
        settings_values = {
            key.removeprefix("GUGABOBO_").lower(): value for key, value in normalized.items()
        }
        try:
            Settings.model_validate(settings_values)
        except ValidationError as error:
            raise ValueError(str(error)) from error
        return normalized

    def _bool_string(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return "true" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "false"
