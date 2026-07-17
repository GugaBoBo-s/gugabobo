import httpx
import pytest

from gugabobo.config import Settings
from gugabobo.infra.code_models import CodeModelRouter, OpenAIResponsesCodeClient


class FakeCodeModel:
    configured = True

    def __init__(self, provider: str, model: str, result: str | Exception) -> None:
        self.provider_name = provider
        self.model = model
        self.result = result
        self.calls = 0

    def complete(self, messages, temperature=0.0):
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
    claude = FakeCodeModel("claude", "claude-code", httpx.ReadTimeout("slow"))
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
    request = httpx.Request("POST", "https://gateway.example/v1/messages")
    response = httpx.Response(504, request=request)
    claude = FakeCodeModel(
        "claude",
        "claude-code",
        httpx.HTTPStatusError("gateway timeout", request=request, response=response),
    )
    openai = FakeCodeModel("openai", "gpt-code", "done")

    result = CodeModelRouter([claude, openai]).complete_with_metadata([])

    assert result.provider == "openai"


def test_openai_code_model_uses_responses_api(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output": [
                    {"content": [{"type": "output_text", "text": "review result"}]}
                ]
            }

    class Client:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return Response()

    monkeypatch.setattr("gugabobo.infra.code_models.httpx.Client", Client)
    client = OpenAIResponsesCodeClient(
        "openai",
        "secret",
        "https://api.openai.com/v1",
        "gpt-code",
        12,
    )

    result = client.complete([{"role": "user", "content": "review"}])

    assert result == "review result"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["payload"] == {
        "model": "gpt-code",
        "input": [{"role": "user", "content": "review"}],
    }
