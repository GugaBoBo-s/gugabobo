import os

from litellm.types.utils import ModelResponse

from gugabobo.config import Settings
from gugabobo.infra.llm import DeepSeekAgentRuntime, MoonshotAgentRuntime


def _response(content, *, tool_calls=None, model="provider-model"):
    return ModelResponse(
        model=model,
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        choices=[
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                }
            }
        ],
    )


def test_pydantic_ai_routes_chat_through_litellm(monkeypatch):
    captured = {}

    async def completion(**kwargs):
        captured.update(kwargs)
        return _response("真实对象响应", model="kimi-k2.6")

    monkeypatch.setattr("pydantic_ai_litellm.litellm_model.acompletion", completion)
    runtime = MoonshotAgentRuntime(
        Settings(
            _env_file=None,
            moonshot_api_key="secret",
            moonshot_base_url="https://moonshot.example/v1",
            moonshot_model="kimi-test",
            llm_timeout_seconds=17,
        )
    )

    result = runtime.run("你好", instructions=["你是测试助手"], temperature=0.7)

    assert result.output == "真实对象响应"
    assert result.model == "kimi-k2.6"
    assert captured["model"] == "openai/kimi-test"
    assert captured["api_base"] == "https://moonshot.example/v1"
    assert captured["api_key"] == "secret"
    assert captured["timeout"] == 17


def test_pydantic_ai_preserves_multimodal_image_content(monkeypatch):
    captured = {}

    async def completion(**kwargs):
        captured.update(kwargs)
        return _response("看到了")

    monkeypatch.setattr("pydantic_ai_litellm.litellm_model.acompletion", completion)
    runtime = MoonshotAgentRuntime(Settings(_env_file=None, moonshot_api_key="secret"))

    runtime.run("看图", images=["data:image/png;base64,Zm9v"])

    user = next(item for item in captured["messages"] if item["role"] == "user")
    assert user["content"] == [
        {"type": "text", "text": "看图"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,Zm9v"},
        },
    ]


def test_pydantic_ai_executes_authorized_tool_loop(monkeypatch):
    calls = []
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "use_gugabobo_tool",
            "arguments": '{"name":"get_current_time","arguments":{}}',
        },
    }

    async def completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _response(None, tool_calls=[tool_call])
        return _response("现在是下午三点。")

    dispatched = []
    monkeypatch.setattr("pydantic_ai_litellm.litellm_model.acompletion", completion)
    runtime = MoonshotAgentRuntime(Settings(_env_file=None, moonshot_api_key="secret"))

    result = runtime.run(
        "现在几点",
        tool_specs=[{"type": "function", "function": {"name": "get_current_time"}}],
        dispatch=lambda name, arguments: dispatched.append((name, arguments)) or "15:00",
    )

    assert result.output == "现在是下午三点。"
    assert dispatched == [("get_current_time", "{}")]
    assert len(calls) == 2


def test_deepseek_runtime_uses_native_provider_prefix():
    runtime = DeepSeekAgentRuntime(
        Settings(
            _env_file=None,
            deepseek_api_key="secret",
            deepseek_model="deepseek-test",
        )
    )

    assert runtime.routed_model == "deepseek/deepseek-test"


def test_litellm_model_cost_map_stays_local():
    import gugabobo.infra  # noqa: F401
    from litellm.litellm_core_utils.get_model_cost_map import (
        get_model_cost_map_source_info,
    )

    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "true"
    source_info = get_model_cost_map_source_info()
    assert source_info["source"] == "local"
    assert source_info["is_env_forced"] is True
