from gugabobo.core.persona import Persona


class ChatSkill:
    def __init__(self, persona: Persona) -> None:
        self.persona = persona

    def reply(self, text: str) -> str:
        if not text.strip():
            return "我在。"
        return f"我是 {self.persona.name}，已收到：{text}"

