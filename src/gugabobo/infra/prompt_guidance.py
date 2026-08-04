from __future__ import annotations

from pathlib import Path


_ALLOWED_DOCUMENTS = {"soul.md", "rules.md"}


class PromptGuidanceStore:
    def __init__(self, directory: Path, max_chars: int) -> None:
        self.directory = directory.resolve()
        self.max_chars = max_chars

    def read(self, name: str) -> str:
        path = self._path(name)
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8")
        if len(content) > self.max_chars:
            raise ValueError(f"{name} 超过 {self.max_chars} 字符限制")
        return content

    def instructions(self) -> list[str]:
        result = []
        for name in ("soul.md", "rules.md"):
            content = self.read(name).strip()
            if content:
                result.append(f"Project guidance from {name}:\n{content}")
        return result

    def replace(self, name: str, content: str) -> str:
        path = self._path(name)
        if len(content) > self.max_chars:
            raise ValueError(f"内容超过 {self.max_chars} 字符限制")
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        return f"已更新 {name}，新内容将在下一条 AI 消息中生效。"

    def _path(self, name: str) -> Path:
        if name not in _ALLOWED_DOCUMENTS:
            raise ValueError("只能访问 soul.md 或 rules.md")
        return self.directory / name
