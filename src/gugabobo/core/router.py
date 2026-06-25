from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    skill: str
    reason: str


class Router:
    def route(self, text: str) -> Route:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ["bug", "建议", "反馈", "问题", "太长"]):
            return Route(skill="feedback", reason="message looks like feedback")
        return Route(skill="chat", reason="default conversational route")

