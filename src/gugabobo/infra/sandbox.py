from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    output: str


def _force_rmtree(path: Path) -> None:
    def on_error(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=on_error)


class SandboxManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def root(self) -> Path:
        return Path(self.settings.sandbox_dir)

    def path_for(self, improvement_id: int) -> Path:
        return self.root / f"improvement-{improvement_id}"

    def prepare(self, improvement_id: int, source_repo: Path, branch: str) -> Path:
        source = Path(source_repo).resolve()
        if not (source / ".git").exists():
            raise SandboxError(f"{source} is not a git repository")
        target = self.path_for(improvement_id)
        if target.exists():
            _force_rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._git(["clone", "--quiet", str(source), str(target)])
        self._git(["checkout", "-q", "-b", branch], cwd=target)
        return target

    def collect_diff(self, path: Path) -> str:
        self._git(["add", "-A"], cwd=path)
        result = self._git(["diff", "--cached"], cwd=path)
        return result.stdout

    def run_checks(self, path: Path) -> CheckResult:
        steps = [
            [sys.executable, "-m", "ruff", "check", "."],
            [sys.executable, "-m", "pytest", "-q"],
        ]
        outputs: list[str] = []
        for command in steps:
            result = subprocess.run(
                command,
                cwd=str(path),
                capture_output=True,
                text=True,
                check=False,
            )
            outputs.append(f"$ {' '.join(command[1:])}\n{result.stdout}{result.stderr}")
            if result.returncode != 0:
                return CheckResult(passed=False, output="\n".join(outputs))
        return CheckResult(passed=True, output="\n".join(outputs))

    def commit_all(self, path: Path, message: str) -> None:
        self._git(["add", "-A"], cwd=path)
        self._git(
            [
                "-c",
                f"user.email={self.settings.git_author_email}",
                "-c",
                f"user.name={self.settings.git_author_name}",
                "commit",
                "-q",
                "-m",
                message,
            ],
            cwd=path,
        )

    def push_branch(self, path: Path, remote_url: str, branch: str) -> None:
        result = subprocess.run(
            ["git", "push", remote_url, f"HEAD:refs/heads/{branch}"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip().replace(remote_url, "<remote>")
            raise SandboxError(f"git push failed: {message}")

    def cleanup(self, improvement_id: int) -> None:
        target = self.path_for(improvement_id)
        if target.exists():
            _force_rmtree(target)

    def _git(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        command = ["git", *args]
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SandboxError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result
