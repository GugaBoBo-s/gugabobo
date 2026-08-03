from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm


@dataclass(frozen=True)
class LiteLLMRequest:
    provider: str
    model: str
    api_key: str
    base_url: str
    timeout: int
    extra_headers: dict[str, str] | None = None

    @property
    def routed_model(self) -> str:
        prefix = f"{self.provider}/"
        return self.model if self.model.startswith(prefix) else f"{prefix}{self.model}"

    def completion(
        self,
        messages: list[dict[str, object]],
        temperature: float,
        tools: list[dict[str, object]] | None = None,
        max_tokens: int | None = None,
    ) -> object:
        kwargs: dict[str, object] = {
            "model": self.routed_model,
            "messages": messages,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        return litellm.completion(**kwargs)

    def responses(self, input_messages: list[dict[str, str]]) -> object:
        kwargs: dict[str, object] = {
            "model": self.routed_model,
            "input": input_messages,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
        }
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        return litellm.responses(**kwargs)


def chat_response_data(
    response: object,
    fallback_model: str,
) -> tuple[str, str, dict[str, object], list[dict[str, object]] | None]:
    response_data = _as_dict(response)
    choices = response_data.get("choices") or getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("LiteLLM response did not contain any choices")
    choice = choices[0]
    choice_data = _as_dict(choice)
    message = choice_data.get("message") or getattr(choice, "message", None)
    message_data = _as_dict(message)
    content = _content_text(message_data.get("content"))
    raw_tool_calls = message_data.get("tool_calls") or []
    tool_calls = [_as_dict(item) for item in raw_tool_calls]
    if tool_calls:
        message_data["tool_calls"] = tool_calls
    model = str(response_data.get("model") or getattr(response, "model", "") or fallback_model)
    return content, model, message_data, tool_calls or None


def responses_output_text(response: object) -> str:
    response_data = _as_dict(response)
    direct = response_data.get("output_text") or getattr(response, "output_text", None)
    if direct:
        return str(direct).strip()
    parts: list[str] = []
    output_items = response_data.get("output") or getattr(response, "output", None) or []
    for output in output_items:
        output_data = _as_dict(output)
        content_items = output_data.get("content") or []
        for content in content_items:
            content_data = _as_dict(content)
            if content_data.get("type") == "output_text" and content_data.get("text"):
                parts.append(str(content_data["text"]))
    if not parts:
        raise ValueError("LiteLLM Responses result did not contain output text")
    return "\n".join(parts).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _content_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content).strip()
    parts: list[str] = []
    for item in content:
        item_data = _as_dict(item)
        text = item_data.get("text")
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()
