from gugabobo.config import Settings
from gugabobo.infra.llm import DeepSeekClient, MoonshotClient
from litellm.types.utils import ModelResponse


def test_litellm_chat_completion_preserves_tools(monkeypatch):
    captured = {}
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "get_current_time", "arguments": "{}"},
    }

    def completion(**kwargs):
        captured.update(kwargs)
        return {
            "model": "kimi-k2.6",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call],
                    }
                }
            ],
        }

    monkeypatch.setattr("gugabobo.infra.litellm_client.litellm.completion", completion)
    settings = Settings(
        _env_file=None,
        moonshot_api_key="secret",
        moonshot_base_url="https://moonshot.example/v1",
        moonshot_model="kimi-test",
        llm_timeout_seconds=17,
    )
    client = MoonshotClient(settings)
    tools = [{"type": "function", "function": {"name": "get_current_time"}}]

    result = client.complete_messages(
        [{"role": "user", "content": "现在几点"}],
        tools=tools,
    )

    assert captured["model"] == "openai/kimi-test"
    assert captured["base_url"] == "https://moonshot.example/v1"
    assert captured["api_key"] == "secret"
    assert captured["timeout"] == 17
    assert captured["tools"] == tools
    assert result.model == "kimi-k2.6"
    assert result.content == ""
    assert result.tool_calls == [tool_call]
    assert result.message == {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call],
    }


def test_litellm_deepseek_completion_uses_native_provider_prefix(monkeypatch):
    captured = {}

    def completion(**kwargs):
        captured.update(kwargs)
        return {
            "model": "deepseek-test",
            "choices": [{"message": {"role": "assistant", "content": "完成"}}],
        }

    monkeypatch.setattr("gugabobo.infra.litellm_client.litellm.completion", completion)
    client = DeepSeekClient(
        Settings(
            _env_file=None,
            deepseek_api_key="secret",
            deepseek_base_url="https://deepseek.example",
            deepseek_model="deepseek-test",
        )
    )

    result = client.complete([{"role": "user", "content": "检查"}])

    assert result == "完成"
    assert captured["model"] == "deepseek/deepseek-test"
    assert captured["base_url"] == "https://deepseek.example"


def test_litellm_model_response_is_normalized(monkeypatch):
    response = ModelResponse(
        model="provider-model",
        choices=[{"message": {"role": "assistant", "content": "真实对象响应"}}],
    )
    monkeypatch.setattr(
        "gugabobo.infra.litellm_client.litellm.completion",
        lambda **kwargs: response,
    )
    client = MoonshotClient(Settings(_env_file=None, moonshot_api_key="secret"))

    result = client.chat("你好", persona=type("Persona", (), {"system_summary": lambda _: ""})())

    assert result.content == "真实对象响应"
    assert result.model == "provider-model"
    assert result.message == {"content": "真实对象响应", "role": "assistant"}
