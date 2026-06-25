from gugabobo.core.persona import Persona
from gugabobo.infra.logs import get_logger
from gugabobo.infra.llm import OpenAICompatibleClient, build_llm_client


class ChatSkill:
    def __init__(self, persona: Persona, llm_client: OpenAICompatibleClient | None = None) -> None:
        self.persona = persona
        self.llm_client = llm_client or build_llm_client()

    def reply(self, text: str, history: list[dict[str, str]] | None = None) -> str:
        if not text.strip():
            return "我在。"
        if self.llm_client.configured:
            try:
                result = self.llm_client.chat(text, self.persona, history=history)
                if result.content:
                    return result.content
            except Exception as exc:
                get_logger().warning("llm chat failed: %s", exc)
        return f"我是 {self.persona.name}，已收到：{text}"
