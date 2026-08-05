from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic_ai import Agent, ImageUrl, Tool, UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai_litellm import LiteLLMModel

from gugabobo.config import Settings, get_settings


OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class AgentResult:
    output: object
    model: str


class MultimodalLiteLLMModel(LiteLLMModel):
    async def _map_messages(self, messages, model_request_parameters):
        mapped = await super()._map_messages(messages, model_request_parameters)
        complex_prompts = [
            part.content
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart) and not isinstance(part.content, str)
        ]
        search_from = 0
        for content in complex_prompts:
            for index in range(search_from, len(mapped)):
                if mapped[index].get("role") == "user":
                    mapped[index]["content"] = _multimodal_content(content)
                    search_from = index + 1
                    break
        return mapped


def _multimodal_content(content: object) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    for item in content if isinstance(content, (list, tuple)) else [content]:
        if isinstance(item, str):
            parts.append({"type": "text", "text": item})
        elif isinstance(item, ImageUrl):
            parts.append({"type": "image_url", "image_url": {"url": item.url}})
        else:
            parts.append({"type": "text", "text": str(item)})
    return parts


class AgentRuntime:
    provider_name = "openai-compatible"
    litellm_provider = "openai"
    api_key_setting = "the selected provider API key"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key(self) -> str:
        raise NotImplementedError

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    @property
    def model(self) -> str:
        raise NotImplementedError

    @property
    def request_timeout(self) -> int:
        return self.settings.llm_timeout_seconds

    @property
    def max_tokens(self) -> int | None:
        return None

    @property
    def routed_model(self) -> str:
        prefix = f"{self.litellm_provider}/"
        return self.model if self.model.startswith(prefix) else f"{prefix}{self.model}"

    def run(
        self,
        text: str,
        *,
        instructions: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
        images: list[str] | None = None,
        tool_specs: list[dict[str, object]] | None = None,
        dispatch: Callable[[str, str], str] | None = None,
        output_type: type[OutputT] | type[str] = str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AgentResult:
        self._ensure_configured()
        tools = self._agent_tools(tool_specs or [], dispatch)
        agent = Agent(
            self._model(),
            output_type=output_type,
            instructions="\n\n".join(item for item in instructions or [] if item.strip()),
            tools=tools,
        )
        prompt: str | list[object] = text
        if images:
            prompt = ([text] if text else []) + [ImageUrl(url) for url in images]
        model_settings: dict[str, object] = {
            "temperature": temperature,
            "timeout": self.request_timeout,
        }
        resolved_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        if resolved_max_tokens is not None:
            model_settings["max_tokens"] = max(1, resolved_max_tokens)
        result = agent.run_sync(
            prompt,
            message_history=_message_history(history or []),
            model_settings=model_settings,
            usage_limits=UsageLimits(request_limit=6, tool_calls_limit=5),
        )
        responses = [item for item in result.all_messages() if isinstance(item, ModelResponse)]
        model = responses[-1].model_name if responses else self.model
        return AgentResult(result.output, model or self.model)

    def run_messages(
        self,
        messages: list[dict[str, str]],
        *,
        output_type: type[OutputT] | type[str] = str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AgentResult:
        system = [item["content"] for item in messages if item["role"] == "system"]
        conversational = [item for item in messages if item["role"] in {"user", "assistant"}]
        if not conversational:
            conversational = [{"role": "user", "content": ""}]
        last_user = next(
            (index for index in range(len(conversational) - 1, -1, -1) if conversational[index]["role"] == "user"),
            len(conversational) - 1,
        )
        prompt = conversational[last_user]["content"]
        history = conversational[:last_user]
        return self.run(
            prompt,
            instructions=system,
            history=history,
            output_type=output_type,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _model(self) -> MultimodalLiteLLMModel:
        return MultimodalLiteLLMModel(
            self.routed_model,
            api_key=self.api_key,
            api_base=self.base_url,
            custom_llm_provider=self.litellm_provider,
        )

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise RuntimeError(
                f"{self.provider_name} API key is not configured; set {self.api_key_setting}"
            )

    def _agent_tools(
        self,
        tool_specs: list[dict[str, object]],
        dispatch: Callable[[str, str], str] | None,
    ) -> list[Tool]:
        if not tool_specs or dispatch is None:
            return []
        descriptions = json.dumps(tool_specs, ensure_ascii=False)

        def use_gugabobo_tool(name: str, arguments: dict[str, Any]) -> str:
            return dispatch(name, json.dumps(arguments, ensure_ascii=False))

        return [
            Tool(
                use_gugabobo_tool,
                name="use_gugabobo_tool",
                description=(
                    "调用一个已授权的 gugabobo 工具。name 必须来自以下工具定义，arguments "
                    f"必须符合对应 JSON Schema：{descriptions}"
                ),
            )
        ]
def _message_history(history: list[dict[str, str]]) -> list[ModelMessage]:
    result: list[ModelMessage] = []
    for item in history:
        if item["role"] == "user":
            result.append(ModelRequest(parts=[UserPromptPart(item["content"])]))
        elif item["role"] == "assistant":
            result.append(ModelResponse(parts=[TextPart(item["content"])]))
    return result


class MoonshotAgentRuntime(AgentRuntime):
    provider_name = "moonshot"
    api_key_setting = "GUGABOBO_MOONSHOT_API_KEY"

    @property
    def api_key(self) -> str:
        return self.settings.moonshot_api_key

    @property
    def base_url(self) -> str:
        return self.settings.moonshot_base_url

    @property
    def model(self) -> str:
        return self.settings.moonshot_model


class DeepSeekAgentRuntime(AgentRuntime):
    provider_name = "deepseek"
    litellm_provider = "deepseek"
    api_key_setting = "GUGABOBO_DEEPSEEK_API_KEY"

    @property
    def api_key(self) -> str:
        return self.settings.deepseek_api_key

    @property
    def base_url(self) -> str:
        return self.settings.deepseek_base_url

    @property
    def model(self) -> str:
        return self.settings.deepseek_model


class OpenAIAgentRuntime(AgentRuntime):
    provider_name = "openai"
    api_key_setting = "GUGABOBO_OPENAI_API_KEY"

    @property
    def api_key(self) -> str:
        return self.settings.openai_api_key

    @property
    def base_url(self) -> str:
        return self.settings.openai_base_url

    @property
    def model(self) -> str:
        return self.settings.openai_model


def build_agent_runtime(settings: Settings | None = None) -> AgentRuntime:
    resolved = settings or get_settings()
    if resolved.llm_provider == "openai":
        return OpenAIAgentRuntime(resolved)
    if resolved.llm_provider == "deepseek":
        return DeepSeekAgentRuntime(resolved)
    return MoonshotAgentRuntime(resolved)
