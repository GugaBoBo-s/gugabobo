from typing import Callable

from gugabobo.core.persona import Persona
from gugabobo.infra.logs import get_logger
from gugabobo.infra.llm import OpenAICompatibleClient, build_llm_client

# Hard cap on tool-call rounds per reply, so a model that keeps asking for tools
# can never spin the loop (and the token bill) forever.
_MAX_TOOL_ROUNDS = 5


class ChatSkill:
    def __init__(self, persona: Persona, llm_client: OpenAICompatibleClient | None = None) -> None:
        self.persona = persona
        self.llm_client = llm_client or build_llm_client()

    def reply(
        self,
        text: str,
        history: list[dict[str, str]] | None = None,
        system_context: list[str] | None = None,
        images: list[str] | None = None,
        tool_specs: list[dict[str, object]] | None = None,
        dispatch: Callable[[str, str], str] | None = None,
    ) -> str:
        if not text.strip() and not images:
            return "我在。"
        if self.llm_client.configured:
            # Tool-calling path: only when tools are offered and there are no
            # images (the relay's tool + vision combo is unverified, so images
            # keep the simple single-shot path).
            if tool_specs and dispatch and not images:
                try:
                    return self._reply_with_tools(
                        text, history or [], system_context or [], tool_specs, dispatch
                    )
                except Exception as exc:
                    get_logger().warning("llm tool loop failed: %s", exc)
            else:
                try:
                    result = self.llm_client.chat(
                        text,
                        self.persona,
                        history=history,
                        system_context=system_context,
                        images=images,
                    )
                    if result.content:
                        return result.content
                except Exception as exc:
                    get_logger().warning("llm chat failed: %s", exc)
        if images and not text:
            return f"我是 {self.persona.name}，收到了图片，但现在看不了。"
        return f"我是 {self.persona.name}，已收到：{text}"

    def _reply_with_tools(
        self,
        text: str,
        history: list[dict[str, str]],
        system_context: list[str],
        tool_specs: list[dict[str, object]],
        dispatch: Callable[[str, str], str],
    ) -> str:
        messages = self.llm_client.build_messages(
            text, self.persona, history, system_context, images=[]
        )
        for _ in range(_MAX_TOOL_ROUNDS):
            result = self.llm_client.complete_messages(messages, tools=tool_specs)
            if not result.tool_calls:
                if result.content:
                    return result.content
                break
            # Append the assistant's tool-call message verbatim, then answer each
            # requested tool with a matching `tool` message (OpenAI protocol).
            messages.append(result.message)
            for call in result.tool_calls:
                function = call.get("function", {})
                name = str(function.get("name", ""))
                arguments = str(function.get("arguments", "") or "")
                output = dispatch(name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": output,
                    }
                )
        # Ran out of rounds (or empty content): make one final call with no tools
        # so the model is forced to produce a text answer from what it gathered.
        final = self.llm_client.complete_messages(messages, tools=None)
        if final.content:
            return final.content
        return f"我是 {self.persona.name}，已收到：{text}"
