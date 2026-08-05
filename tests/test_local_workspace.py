import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from gugabobo.config import Settings
from gugabobo.core.local_operator import LocalOperatorResult
from gugabobo.core.tools import (
    ToolContext,
    ToolRegistry,
    local_delegation_tool,
    local_tools,
)
from gugabobo.infra.local_workspace import LocalWorkspace
from gugabobo.memory.store import MemoryStore


def make_workspace(tmp_path, **overrides):
    values = {
        "local_workspace_dir": tmp_path / "workspace",
        "local_skill_dir": tmp_path / "skills",
        "local_command_allowlist": "python,python.exe",
        "local_output_max_chars": 12000,
    }
    values.update(overrides)
    workspace = values["local_workspace_dir"]
    workspace.mkdir(parents=True, exist_ok=True)
    return LocalWorkspace(Settings(_env_file=None, **values))


def test_workspace_files_stay_inside_root_and_block_secrets(tmp_path):
    workspace = make_workspace(tmp_path)
    workspace.write_text("notes/demo.txt", "hello")

    assert workspace.read_text("notes/demo.txt") == "hello"
    assert "notes/demo.txt" in workspace.list_files()
    with pytest.raises(ValueError, match="超出"):
        workspace.read_text("../outside.txt")
    with pytest.raises(ValueError, match="敏感文件"):
        workspace.write_text(".env", "SECRET=x")


def test_run_python_uses_current_virtual_environment(tmp_path):
    workspace = make_workspace(tmp_path)

    result = workspace.run(["python", "-c", "import sys; print(sys.executable)"])

    assert result.returncode == 0
    assert result.stdout.strip() == sys.executable


def test_run_bash_uses_real_shell(tmp_path):
    workspace = make_workspace(
        tmp_path,
        local_command_allowlist="bash,bash.exe",
        local_bash_enabled=True,
    )

    result = workspace.run(["bash", "-lc", "printf bash-ok"])

    assert result.returncode == 0
    assert result.stdout == "bash-ok"


def test_bash_requires_separate_opt_in(tmp_path):
    workspace = make_workspace(tmp_path, local_command_allowlist="bash,bash.exe")

    with pytest.raises(ValueError, match="LOCAL_BASH_ENABLED"):
        workspace.run(["bash", "-lc", "printf should-not-run"])


def test_local_process_does_not_inherit_unlisted_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_FAKE_SECRET", "do-not-inherit")
    workspace = make_workspace(tmp_path)

    result = workspace.run(
        [
            "python",
            "-c",
            "import os; print(os.environ.get('GUGABOBO_FAKE_SECRET', 'missing'))",
        ]
    )

    assert result.stdout.strip() == "missing"


def test_command_allowlist_rejects_other_executables(tmp_path):
    workspace = make_workspace(tmp_path)

    with pytest.raises(ValueError, match="允许列表"):
        workspace.run(["git", "status"])


def test_install_skill_downloads_then_validates_skill_file(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)

    def fake_clone(argv, **_kwargs):
        target = Path(argv[-1])
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("gugabobo.infra.local_workspace.subprocess.run", fake_clone)

    target = workspace.install_skill("demo", "https://github.com/example/demo.git")

    assert target.name == "demo"
    assert workspace.list_skills() == ["demo"]
    assert workspace.read_skill("demo") == "# Demo\n"


def test_install_skill_removes_invalid_download(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)

    def fake_clone(argv, **_kwargs):
        Path(argv[-1]).mkdir(parents=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("gugabobo.infra.local_workspace.subprocess.run", fake_clone)

    with pytest.raises(ValueError, match="缺少 SKILL.md"):
        workspace.install_skill("bad", "https://github.com/example/bad.git")

    assert not (workspace.skill_dir / ".bad.partial").exists()


def test_tabhere_file_references_only_expand_allowlisted_paths(tmp_path):
    workspace = make_workspace(
        tmp_path,
        tabhere_file_context_enabled=True,
        tabhere_file_allowlist="docs/**",
    )
    workspace.write_text("docs/context.txt", "allowed")
    workspace.write_text("private.txt", "blocked")

    messages = workspace.expand_file_references(
        [{"role": "user", "content": "参考 @file:docs/context.txt 和 @file:private.txt"}]
    )

    assert messages[0]["role"] == "system"
    assert "allowed" in messages[0]["content"]
    assert "blocked" not in messages[0]["content"]


def test_local_tools_are_owner_only_and_audited(tmp_path):
    workspace = make_workspace(tmp_path)
    store = MemoryStore(tmp_path / "tools.db")
    registry = ToolRegistry(local_tools())
    owner = ToolContext(
        store=store,
        conversation_id="cli:owner",
        access_role="owner",
        source="cli",
        user_id="owner",
        local_workspace=workspace,
    )
    user = ToolContext(
        store=store,
        conversation_id="api:user",
        access_role="user",
        local_workspace=workspace,
    )

    denied = registry.dispatch("run_local", '{"argv":["python","-V"]}', user)
    output = registry.dispatch(
        "run_local",
        json.dumps({"argv": ["python", "-c", "print('ok')"]}),
        owner,
    )

    assert "不能使用" in denied
    assert json.loads(output)["stdout"] == "ok\n"
    assert store.list_audit_logs(limit=10)[0]["action"] == "tool.run_local"


def test_main_agent_only_gets_delegation_tool(tmp_path):
    class FakeOperator:
        def run(self, task, context):
            assert task == "运行测试"
            return LocalOperatorResult("测试通过", "claude", "opus", 2)

    store = MemoryStore(tmp_path / "delegate.db")
    registry = ToolRegistry([local_delegation_tool()])
    context = ToolContext(
        store=store,
        conversation_id="cli:owner",
        access_role="owner",
        source="cli",
        user_id="owner",
        local_operator=FakeOperator(),
    )

    output = registry.dispatch(
        "delegate_local_agent",
        json.dumps({"task": "运行测试"}, ensure_ascii=False),
        context,
    )

    assert output == "测试通过"
    assert {spec["function"]["name"] for spec in registry.specs_for("owner")} == {
        "delegate_local_agent"
    }
    audit = store.list_audit_logs(limit=1)[0]
    assert audit["action"] == "tool.delegate_local_agent"
    assert '"provider": "claude"' in audit["detail"]


def test_run_rejects_a_path_in_argv0(tmp_path) -> None:
    workspace = make_workspace(tmp_path)

    for candidate in (
        "/tmp/evil/python",
        "../../evil/python",
        "C:/attacker/python.exe",
        r"dir\python",
    ):
        with pytest.raises(ValueError, match="不能包含路径"):
            workspace.run([candidate, "-V"])


def test_run_still_accepts_a_bare_allowlisted_command(tmp_path) -> None:
    workspace = make_workspace(tmp_path)

    result = workspace.run(["python", "-V"])

    assert result.returncode == 0
    assert "Python" in result.stdout + result.stderr


def test_tabhere_allowlist_rejects_parent_traversal(tmp_path) -> None:
    workspace = make_workspace(
        tmp_path,
        tabhere_file_context_enabled=True,
        tabhere_file_allowlist="README.md,docs/**",
    )

    assert workspace._tabhere_path_allowed("README.md") is True
    assert workspace._tabhere_path_allowed("docs/guide.md") is True
    assert workspace._tabhere_path_allowed("./docs/guide.md") is True
    assert workspace._tabhere_path_allowed("docs/../.git-credentials") is False
    assert workspace._tabhere_path_allowed("docs/../../secret") is False


def test_sensitive_rejection_covers_env_backups_and_credentials(tmp_path) -> None:
    workspace = make_workspace(tmp_path)

    for name in (
        ".env",
        ".env.bak.20260804040049",
        ".env.production",
        ".git-credentials",
        ".npmrc",
        ".pypirc",
        "secrets.yaml",
        "service.pem",
        "id_rsa",
    ):
        with pytest.raises(ValueError, match="敏感文件"):
            workspace.read_text(name)

    # Substring rules such as `*token*` would reject these, which would make any
    # workspace holding tokenizer code unusable.
    for name in (
        "README.md",
        "docs/guide.md",
        "pyproject.toml",
        "tokenizer.py",
        "token_utils.py",
        "src/tokenizer/model.py",
        "credentials_guide.md",
        "id_generator.py",
    ):
        workspace.write_text(name, "ok")
        assert workspace.read_text(name) == "ok"


def test_workspace_containing_own_source_is_refused(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace = LocalWorkspace(
        Settings(
            _env_file=None,
            local_workspace_dir=repo_root,
            local_skill_dir=tmp_path / "skills",
            local_command_allowlist="python",
        )
    )

    assert workspace.contains_own_source is True
    for call in (
        lambda: workspace.list_files("."),
        lambda: workspace.read_text("README.md"),
        lambda: workspace.write_text("scratch.txt", "x"),
        lambda: workspace.run(["python", "-V"]),
    ):
        with pytest.raises(ValueError, match="自身源码"):
            call()
