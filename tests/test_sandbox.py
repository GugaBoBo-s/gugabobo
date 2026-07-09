import subprocess

from gugabobo.config import get_settings
from gugabobo.infra.sandbox import SandboxManager


def init_source_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "readme.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=path,
        check=True,
    )
    return path


def configure_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_SANDBOX_DIR", str(tmp_path / "sandbox"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "data" / "db.sqlite"))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    get_settings.cache_clear()


def test_prepare_clones_and_branches(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    source = init_source_repo(tmp_path / "source")
    manager = SandboxManager()

    path = manager.prepare(1, source, "gugabobo/improvement-1")

    assert path.exists()
    assert (path / "readme.txt").exists()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert branch.stdout.strip() == "gugabobo/improvement-1"
    get_settings.cache_clear()


def test_collect_diff_detects_new_file(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    source = init_source_repo(tmp_path / "source")
    manager = SandboxManager()
    path = manager.prepare(2, source, "gugabobo/improvement-2")

    (path / "new.py").write_text("print('hi')\n", encoding="utf-8")
    diff = manager.collect_diff(path)

    assert "new.py" in diff
    assert "print('hi')" in diff
    get_settings.cache_clear()


def test_cleanup_removes_sandbox(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    source = init_source_repo(tmp_path / "source")
    manager = SandboxManager()
    path = manager.prepare(3, source, "gugabobo/improvement-3")
    assert path.exists()

    manager.cleanup(3)

    assert not path.exists()
    get_settings.cache_clear()


def test_commit_all_commits_changes(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    source = init_source_repo(tmp_path / "source")
    manager = SandboxManager()
    path = manager.prepare(4, source, "gugabobo/improvement-4")
    (path / "added.py").write_text("x = 1\n", encoding="utf-8")

    manager.commit_all(path, "feat: add file")

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "feat: add file" in log.stdout
    diff_after = manager.collect_diff(path)
    assert diff_after.strip() == ""
    get_settings.cache_clear()


def test_run_checks_reports_pass_and_fail(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    from gugabobo.infra import sandbox as sandbox_module

    manager = SandboxManager()

    monkeypatch.setattr(
        sandbox_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="ok", stderr=""),
    )
    passed = manager.run_checks(tmp_path)
    assert passed.passed is True

    monkeypatch.setattr(
        sandbox_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout="", stderr="fail"),
    )
    failed = manager.run_checks(tmp_path)
    assert failed.passed is False
    assert "fail" in failed.output
    get_settings.cache_clear()
