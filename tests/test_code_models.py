import pytest
from litellm.exceptions import Timeout as LiteLLMTimeout

from gugabobo.config import Settings
from gugabobo.infra.code_models import CodeModelRouter, PydanticCodeAgent


class FakeCodeModel:
    configured = True

    def __init__(self, provider: str, model: str, result: str | Exception) -> None:
        self.provider_name = provider
        self.model = model
        self.result = result
        self.calls = 0

    def complete(self, messages, temperature=0.0, output_type=str):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_code_model_defaults_use_latest_primary_and_fallback_models():
    settings = Settings(_env_file=None)

    assert settings.code_claude_model == "claude-opus-4-8"
    assert settings.code_openai_model == "gpt-5.6-sol"


def test_code_model_uses_claude_without_calling_fallbacks():
    claude = FakeCodeModel("claude", "claude-code", "done")
    openai = FakeCodeModel("openai", "gpt-code", "fallback")
    deepseek = FakeCodeModel("deepseek", "deepseek-code", "last")

    result = CodeModelRouter([claude, openai, deepseek]).complete_with_metadata([])

    assert result.content == "done"
    assert result.provider == "claude"
    assert [claude.calls, openai.calls, deepseek.calls] == [1, 0, 0]


def test_code_model_falls_back_in_order_only_on_timeouts():
    claude = FakeCodeModel(
        "claude",
        "claude-code",
        LiteLLMTimeout("slow", model="claude-code", llm_provider="anthropic"),
    )
    openai = FakeCodeModel("openai", "gpt-code", TimeoutError("slow"))
    deepseek = FakeCodeModel("deepseek", "deepseek-code", "done")

    result = CodeModelRouter([claude, openai, deepseek]).complete_with_metadata([])

    assert result.provider == "deepseek"
    assert [claude.calls, openai.calls, deepseek.calls] == [1, 1, 1]


def test_code_model_does_not_fallback_on_non_timeout_error():
    claude = FakeCodeModel("claude", "claude-code", RuntimeError("unauthorized"))
    openai = FakeCodeModel("openai", "gpt-code", "fallback")

    with pytest.raises(RuntimeError, match="unauthorized"):
        CodeModelRouter([claude, openai]).complete([])

    assert openai.calls == 0


def test_code_model_treats_gateway_timeout_status_as_timeout():
    class GatewayTimeout(RuntimeError):
        status_code = 504

    claude = FakeCodeModel("claude", "claude-code", GatewayTimeout("gateway timeout"))
    openai = FakeCodeModel("openai", "gpt-code", "done")

    result = CodeModelRouter([claude, openai]).complete_with_metadata([])

    assert result.provider == "openai"


def test_openai_code_model_is_a_pydantic_ai_agent():
    client = PydanticCodeAgent(
        Settings(_env_file=None, code_model_timeout_seconds=12),
        "openai",
        "openai",
        "secret",
        "GUGABOBO_OPENAI_API_KEY",
        "https://api.openai.com/v1",
        "gpt-code",
    )

    assert client.routed_model == "openai/gpt-code"
    assert client.request_timeout == 12
