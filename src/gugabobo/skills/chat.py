from typing import Callable

from gugabobo.core.persona import Persona
from gugabobo.infra.llm import AgentRuntime, build_agent_runtime
from gugabobo.infra.logs import get_logger
from gugabobo.infra.prompt_guidance import PromptGuidanceStore
from gugabobo.config import get_settings


class ChatSkill:
    def __init__(self, persona: Persona, llm_client: AgentRuntime | None = None) -> None:
        self.persona = persona
        self.runtime = llm_client or build_agent_runtime()
        settings = get_settings()
        self.guidance = PromptGuidanceStore(
            settings.prompt_guidance_dir,
            settings.prompt_guidance_max_chars,
        )

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
        if self.runtime.configured:
            try:
                result = self.runtime.run(
                    text,
                    instructions=[
                        self.persona.system_summary(),
                        *self.guidance.instructions(),
                        *(system_context or []),
                    ],
                    history=history,
                    images=images,
                    tool_specs=tool_specs,
                    dispatch=dispatch,
                    temperature=0.7,
                )
                content = str(result.output).strip()
                if content:
                    return content
            except Exception as exc:
                get_logger().warning("Pydantic AI chat failed: %s", exc)
        if images and not text:
            return f"我是 {self.persona.name}，收到了图片，但现在看不了。"
        return f"我是 {self.persona.name}，已收到：{text}"
