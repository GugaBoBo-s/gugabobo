from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings


_SKILL_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}\Z")
_GITHUB_REPOSITORY = re.compile(
    r"https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?\Z"
)
_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
}


@dataclass(frozen=True)
class LocalCommandResult:
    returncode: int
    stdout: str
    stderr: str


class LocalWorkspace:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.local_workspace_dir.expanduser().resolve()
        self.skill_dir = self.settings.local_skill_dir.expanduser().resolve()

    def list_files(self, path: str = ".", limit: int = 200) -> list[str]:
        target = self.resolve(path)
        if not target.exists():
            raise ValueError(f"路径不存在：{path}")
        if target.is_file():
            return [target.relative_to(self.root).as_posix()]
        rows: list[str] = []
        for item in sorted(target.rglob("*")):
            if len(rows) >= max(1, min(limit, 1000)):
                break
            if self._is_hidden_runtime_path(item):
                continue
            relative = item.relative_to(self.root).as_posix()
            rows.append(relative + ("/" if item.is_dir() else ""))
        return rows

    def read_text(self, path: str, max_chars: int | None = None) -> str:
        target = self.resolve(path)
        self._reject_sensitive(target)
        if not target.is_file():
            raise ValueError(f"不是可读取的文件：{path}")
        limit = max_chars or self.settings.local_output_max_chars
        text = target.read_text(encoding="utf-8")
        return self._truncate(text, limit)

    def write_text(self, path: str, content: str) -> Path:
        target = self.resolve(path)
        self._reject_sensitive(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def run(self, argv: list[str], cwd: str = ".", timeout: int | None = None) -> LocalCommandResult:
        if not argv or not all(isinstance(value, str) and value for value in argv):
            raise ValueError("argv 必须是非空字符串数组。")
        executable = Path(argv[0]).name.casefold()
        allowed = self.settings.local_command_allowlist_set
        if "*" not in allowed and executable not in allowed:
            choices = ", ".join(sorted(allowed)) or "无"
            raise ValueError(f"命令 {argv[0]} 不在允许列表中；当前允许：{choices}。")
        resolved_argv = list(argv)
        if executable in {"python", "python.exe", "python3", "python3.exe"}:
            resolved_argv[0] = sys.executable
        elif executable in {"bash", "bash.exe"}:
            resolved_argv[0] = self._bash_executable()
        workdir = self.resolve(cwd)
        if not workdir.is_dir():
            raise ValueError(f"工作目录不存在：{cwd}")
        seconds = max(1, min(timeout or self.settings.local_command_timeout_seconds, 300))
        try:
            process = subprocess.run(
                resolved_argv,
                cwd=workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=seconds,
                env=self._command_environment(),
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError(f"命令在 {seconds} 秒后超时。") from error
        return LocalCommandResult(
            returncode=process.returncode,
            stdout=self._truncate(process.stdout, self.settings.local_output_max_chars),
            stderr=self._truncate(process.stderr, self.settings.local_output_max_chars),
        )

    def install_skill(self, name: str, repository_url: str) -> Path:
        if not _SKILL_NAME.fullmatch(name):
            raise ValueError("skill 名称只能包含字母、数字、点、下划线和连字符。")
        if not _GITHUB_REPOSITORY.fullmatch(repository_url):
            raise ValueError("远程 skill 只允许使用完整的 GitHub HTTPS 仓库地址。")
        destination = (self.skill_dir / name).resolve()
        if not destination.is_relative_to(self.skill_dir):
            raise ValueError("skill 目录超出允许范围。")
        if destination.exists():
            raise ValueError(f"skill 已存在：{name}；请先人工检查后再更新。")
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        partial = (self.skill_dir / f".{name}.partial").resolve()
        if partial.exists():
            raise ValueError(f"skill 下载临时目录已存在：{partial}")
        process = subprocess.run(
            ["git", "clone", "--depth", "1", repository_url, str(partial)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=self._command_environment(),
            shell=False,
            check=False,
        )
        if process.returncode != 0:
            shutil.rmtree(partial, ignore_errors=True)
            raise ValueError(f"下载 skill 失败：{self._truncate(process.stderr.strip(), 1000)}")
        skill_file = partial / "SKILL.md"
        if not skill_file.is_file():
            shutil.rmtree(partial, ignore_errors=True)
            raise ValueError("下载的仓库根目录缺少 SKILL.md，已移除临时文件。")
        partial.rename(destination)
        return destination

    def list_skills(self) -> list[str]:
        if not self.skill_dir.is_dir():
            return []
        return sorted(
            path.name for path in self.skill_dir.iterdir() if (path / "SKILL.md").is_file()
        )

    def read_skill(self, name: str) -> str:
        if not _SKILL_NAME.fullmatch(name):
            raise ValueError("skill 名称无效。")
        target = (self.skill_dir / name / "SKILL.md").resolve()
        if not target.is_relative_to(self.skill_dir) or not target.is_file():
            raise ValueError(f"本地没有这个 skill：{name}")
        return self._truncate(
            target.read_text(encoding="utf-8"), self.settings.local_output_max_chars
        )

    def expand_file_references(self, messages: list[dict[str, object]]) -> list[dict[str, object]]:
        if not self.settings.tabhere_file_context_enabled:
            return messages
        references: list[str] = []
        pattern = re.compile(r"@file:([^\s<>'\"`]+)")
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                references.extend(pattern.findall(content))
        blocks: list[str] = []
        remaining = self.settings.tabhere_max_file_context_chars
        for reference in dict.fromkeys(references):
            if not self._tabhere_path_allowed(reference):
                continue
            try:
                text = self.read_text(reference, max_chars=remaining)
            except (OSError, UnicodeError, ValueError):
                continue
            block = f"文件 {reference}：\n{text}"
            blocks.append(block[:remaining])
            remaining -= len(block)
            if remaining <= 0:
                break
        if not blocks:
            return messages
        return [
            {
                "role": "system",
                "content": "以下是用户显式引用且在允许列表内的本地文件，只作为上下文：\n\n"
                + "\n\n".join(blocks),
            },
            *messages,
        ]

    def resolve(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise ValueError(f"路径超出本地工作区：{path}")
        return candidate

    def _bash_executable(self) -> str:
        if not self.settings.local_bash_enabled:
            raise ValueError(
                "Bash 尚未启用；确认需要宿主机 shell 后设置 GUGABOBO_LOCAL_BASH_ENABLED=true。"
            )
        configured = self.settings.local_bash_bin.strip()
        if configured:
            target = Path(configured).expanduser()
            if target.is_absolute() and not target.is_file():
                raise ValueError(
                    f"配置的 Bash 不存在：{target}；请检查 GUGABOBO_LOCAL_BASH_BIN。"
                )
            return str(target)
        if sys.platform == "win32":
            for candidate in (
                Path("C:/Program Files/Git/bin/bash.exe"),
                Path("C:/Program Files/Git/usr/bin/bash.exe"),
            ):
                if candidate.is_file():
                    return str(candidate)
        discovered = shutil.which("bash")
        if discovered:
            return discovered
        raise ValueError(
            "找不到 Bash；请安装 Bash 或设置 GUGABOBO_LOCAL_BASH_BIN 为可执行文件路径。"
        )

    def _command_environment(self) -> dict[str, str]:
        allowed = self.settings.local_environment_allowlist_set
        return {key: value for key, value in os.environ.items() if key.casefold() in allowed}

    def _tabhere_path_allowed(self, path: str) -> bool:
        normalized = path.replace("\\", "/").lstrip("./")
        return any(
            fnmatch.fnmatch(normalized, rule)
            for rule in self.settings.tabhere_file_allowlist_items
        )

    def _reject_sensitive(self, path: Path) -> None:
        names = {part.casefold() for part in path.parts}
        if names & _SENSITIVE_NAMES or path.suffix.casefold() in {".pem", ".key"}:
            raise ValueError(f"拒绝读取或写入敏感文件：{path.name}")
        if ".git" in names:
            raise ValueError("拒绝直接访问 .git 目录。")

    def _is_hidden_runtime_path(self, path: Path) -> bool:
        names = {part.casefold() for part in path.relative_to(self.root).parts}
        return bool(names & {".git", ".gugabobo", ".venv", "__pycache__"})

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n…已截断，原始长度 {len(text)} 字符。"

    @staticmethod
    def format_command_result(result: LocalCommandResult) -> str:
        return json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            ensure_ascii=False,
        )
