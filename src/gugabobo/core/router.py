from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    skill: str
    reason: str


class Router:
    def route(self, text: str) -> Route:
        lowered = text.lower()
        memory_prefixes = ["记住", "请记住", "你要记住", "帮我记住", "remember"]
        if any(lowered.startswith(prefix.lower()) for prefix in memory_prefixes):
            return Route(skill="memory", reason="explicit memory request")
        if any(keyword in lowered for keyword in ["bug", "建议", "反馈", "问题", "太长"]):
            return Route(skill="feedback", reason="message looks like feedback")
        return Route(skill="chat", reason="default conversational route")
