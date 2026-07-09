from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings


@dataclass(frozen=True)
class RunResult:
    ok: bool
    output: str
    error: str = ""


class ClaudeCodeRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return shutil.which(self.settings.claude_bin) is not None

    def run(self, prompt: str, cwd: Path) -> RunResult:
        command = [
            self.settings.claude_bin,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            self.settings.claude_permission_mode,
        ]
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                timeout=self.settings.claude_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return RunResult(ok=False, output="", error="claude run timed out")
        return RunResult(
            ok=result.returncode == 0,
            output=result.stdout,
            error=result.stderr,
        )
