import json

import pytest

from gugabobo.config import Settings
from gugabobo.core.local_operator import LocalOperatorAgent
from gugabobo.core.tools import ToolContext
from gugabobo.infra.code_models import CodeModelResult
from gugabobo.infra.local_workspace import LocalWorkspace
from gugabobo.memory.store import MemoryStore


class FakeCodeRouter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete_with_metadata(self, messages, temperature=0.0):
        self.calls.append(messages)
        return CodeModelResult(self.outputs.pop(0), "claude", "opus")


def make_context(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    settings = Settings(
        _env_file=None,
        local_workspace_dir=root,
        local_skill_dir=tmp_path / "skills",
        local_command_allowlist="python,python.exe",
    )
    return settings, ToolContext(
        store=MemoryStore(tmp_path / "operator.db"),
        conversation_id="cli:owner",
        access_role="owner",
        source="cli",
        user_id="owner",
        local_workspace=LocalWorkspace(settings),
    )


def test_local_operator_executes_actions_then_reports(tmp_path):
    settings, context = make_context(tmp_path)
    router = FakeCodeRouter(
        [
            json.dumps(
                {
                    "actions": [
                        {
                            "tool": "run_local",
                            "arguments": {"argv": ["python", "-c", "print('ok')"]},
                        }
                    ],
                    "answer": "",
                }
            ),
            json.dumps({"actions": [], "answer": "命令成功输出 ok。"}, ensure_ascii=False),
        ]
    )
    operator = LocalOperatorAgent(settings, model_router=router)

    result = operator.run("运行 Python", context)

    assert result.answer == "命令成功输出 ok。"
    assert result.provider == "claude"
    assert result.rounds == 2
    second_call = router.calls[1]
    tool_results = json.loads(second_call[-1]["content"].removeprefix("本轮工具结果："))
    assert json.loads(tool_results[0]["output"])["stdout"] == "ok\n"


def test_local_operator_rejects_non_json_model_output(tmp_path):
    settings, context = make_context(tmp_path)
    operator = LocalOperatorAgent(settings, model_router=FakeCodeRouter(["not json"]))

    with pytest.raises(ValueError, match="有效 JSON"):
        operator.run("运行 Python", context)


def test_local_operator_stops_at_round_limit(tmp_path):
    settings, context = make_context(tmp_path)
    settings = settings.model_copy(update={"local_subagent_max_rounds": 1})
    action = json.dumps(
        {
            "actions": [
                {
                    "tool": "workspace_files",
                    "arguments": {"action": "list", "path": "."},
                }
            ],
            "answer": "",
        }
    )
    operator = LocalOperatorAgent(settings, model_router=FakeCodeRouter([action]))

    with pytest.raises(ValueError, match="达到 1 轮上限"):
        operator.run("持续检查", context)
