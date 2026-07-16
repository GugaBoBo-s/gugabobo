from pathlib import Path


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
    "GUGABOBO_GITHUB_OWNER",
    "GUGABOBO_GITHUB_REPO",
    "GUGABOBO_GITHUB_API_URL",
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
}

BOOLEAN_CONFIG_KEYS = {
    "GUGABOBO_NAPCAT_REPLY_ENABLED",
    "GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED",
    "GUGABOBO_TELEGRAM_REPLY_ENABLED",
}

INTEGER_CONFIG_KEYS = {
    "GUGABOBO_LLM_TIMEOUT_SECONDS",
    "GUGABOBO_LLM_CONTEXT_MESSAGES",
    "GUGABOBO_LLM_MEMORY_ITEMS",
    "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET",
    "GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS",
    "GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS",
}

INTEGER_CONFIG_MINIMUMS = {
    "GUGABOBO_LLM_TIMEOUT_SECONDS": 1,
    "GUGABOBO_LLM_CONTEXT_MESSAGES": 1,
    "GUGABOBO_LLM_MEMORY_ITEMS": 0,
    "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET": 1,
    "GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS": 1,
    "GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS": 0,
}


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
        self.path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
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
                normalized[key] = str(max(INTEGER_CONFIG_MINIMUMS[key], int(value)))
                continue
            normalized[key] = str(value).replace("\r", "").replace("\n", "").strip()
        return normalized

    def _bool_string(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return "true" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "false"
