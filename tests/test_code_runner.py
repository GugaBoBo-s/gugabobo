from gugabobo.infra.claude_runner import RunResult
from gugabobo.infra.code_runner import CodeRunnerChain


class FakeRunner:
    configured = True

    def __init__(self, result: RunResult) -> None:
        self.result = result
        self.calls = 0

    def run(self, prompt, cwd):
        self.calls += 1
        return self.result


def test_code_runner_falls_back_after_two_timeouts(tmp_path):
    claude = FakeRunner(RunResult(False, "", "slow", True, "claude", "c"))
    openai = FakeRunner(RunResult(False, "", "slow", True, "openai", "g"))
    deepseek = FakeRunner(RunResult(True, "done", provider="deepseek", model="d"))

    result = CodeRunnerChain([claude, openai, deepseek]).run("fix", tmp_path)

    assert result.ok is True
    assert result.provider == "deepseek"
    assert [claude.calls, openai.calls, deepseek.calls] == [1, 1, 1]


def test_code_runner_stops_on_non_timeout_failure(tmp_path):
    claude = FakeRunner(RunResult(False, "", "auth failed", False, "claude", "c"))
    openai = FakeRunner(RunResult(True, "done", provider="openai", model="g"))

    result = CodeRunnerChain([claude, openai]).run("fix", tmp_path)

    assert result.error == "auth failed"
    assert openai.calls == 0
