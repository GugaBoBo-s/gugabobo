from gugabobo.memory.store import MemoryStore


MEMORY_PREFIXES = (
    "记住",
    "请记住",
    "你要记住",
    "帮我记住",
    "remember",
)


class MemorySkill:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def extract_memory_content(self, text: str) -> str | None:
        stripped = text.strip()
        lowered = stripped.lower()
        for prefix in MEMORY_PREFIXES:
            if lowered.startswith(prefix.lower()):
                content = stripped[len(prefix) :].strip(" ：:，,。")
                return content or None
        return None

    def record(self, text: str, subject: str) -> str:
        content = self.extract_memory_content(text)
        if not content:
            return "你想让我记住什么？可以说：记住 用户喜欢蓝色。"
        memory_id = self.store.add_memory_item(
            subject=subject,
            content=content,
            memory_type="explicit",
            importance=8,
            source="explicit_user_request",
        )
        return f"已记住：{content}（记忆 #{memory_id}）"
