from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from gugabobo.config import Settings, get_settings
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.infra.redaction import redact_sensitive


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
    def __init__(
        self,
        settings: Settings | None = None,
        container_runtime: ContainerRuntime | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.container_runtime = container_runtime or ContainerRuntime(self.settings)

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
        self._git(["clone", "--quiet", "--no-hardlinks", str(source), str(target)])
        self._git(["checkout", "-q", "-b", branch], cwd=target)
        return target

    def prepare_remote(
        self,
        improvement_id: int,
        remote_url: str,
        branch: str,
        token: str,
    ) -> Path:
        if not token:
            raise SandboxError("GitHub token is not configured")
        target = self.path_for(improvement_id)
        if target.exists():
            _force_rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gugabobo-askpass-") as temp_dir:
            askpass = self._write_askpass(Path(temp_dir))
            env = self._git_auth_environment(askpass, token)
            result = subprocess.run(
                ["git", "clone", "--quiet", remote_url, str(target)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        if result.returncode != 0:
            message = redact_sensitive(result.stderr, (token, remote_url))
            raise SandboxError(f"git clone failed: {message.strip()}")
        self._git(["checkout", "-q", "-b", branch], cwd=target)
        return target

    def collect_diff(self, path: Path) -> str:
        self._git(["add", "-A"], cwd=path)
        result = self._git(["diff", "--cached"], cwd=path)
        return result.stdout

    def run_checks(self, path: Path) -> CheckResult:
        if not self.container_runtime.ready:
            return CheckResult(
                passed=False,
                output="isolated test runner is unavailable; host execution is disabled",
            )
        steps = [
            ["python", "-m", "ruff", "check", "."],
            ["python", "-m", "pytest", "-q"],
        ]
        outputs: list[str] = []
        for command in steps:
            result = self.container_runtime.run(
                workspace=path,
                command=command,
                network="none",
                timeout=self.settings.sandbox_check_timeout_seconds,
            )
            outputs.append(f"$ {' '.join(command)}\n{result.stdout}{result.stderr}")
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

    def push_branch(self, path: Path, remote_url: str, branch: str, token: str) -> None:
        if not token:
            raise SandboxError("GitHub token is not configured")
        with tempfile.TemporaryDirectory(prefix="gugabobo-askpass-") as temp_dir:
            askpass = self._write_askpass(Path(temp_dir))
            env = self._git_auth_environment(askpass, token)
            result = subprocess.run(
                ["git", "push", remote_url, f"HEAD:refs/heads/{branch}"],
                cwd=str(path),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        if result.returncode != 0:
            message = redact_sensitive(result.stderr, (token, remote_url))
            raise SandboxError(f"git push failed: {message.strip()}")

    def _git_auth_environment(self, askpass: Path, token: str) -> dict[str, str]:
        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(askpass)
        env["GIT_ASKPASS_USERNAME"] = "x-access-token"
        env["GIT_ASKPASS_PASSWORD"] = token
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env

    def cleanup(self, improvement_id: int) -> None:
        target = self.path_for(improvement_id)
        if target.exists():
            _force_rmtree(target)

    def _write_askpass(self, directory: Path) -> Path:
        if os.name == "nt":
            path = directory / "askpass.cmd"
            path.write_text(
                "@echo off\r\n"
                "echo %~1 | findstr /I \"Username\" >nul\r\n"
                "if %errorlevel%==0 (echo %GIT_ASKPASS_USERNAME%) else (echo %GIT_ASKPASS_PASSWORD%)\r\n",
                encoding="utf-8",
            )
            return path
        path = directory / "askpass.sh"
        path.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "*Username*) printf '%s\\n' \"$GIT_ASKPASS_USERNAME\" ;;\n"
            "*) printf '%s\\n' \"$GIT_ASKPASS_PASSWORD\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return path

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
