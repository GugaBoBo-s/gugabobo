from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    skill: str
    reason: str


class Router:
    # These prefixes trigger feedback when the message *starts* with one of
    # them. Substring matching ("建议" anywhere) is too broad: "这电影我建议
    # 你看看" or "这问题挺难的" would be misrouted.
    _FEEDBACK_PREFIXES = (
        "bug",
        "建议",
        "反馈",
        "吐槽",
        "回复太长",
        "太长了",
    )

    def route(self, text: str) -> Route:
        lowered = text.lower().strip()
        memory_prefixes = ["记住", "请记住", "你要记住", "帮我记住", "remember"]
        if any(lowered.startswith(prefix.lower()) for prefix in memory_prefixes):
            return Route(skill="memory", reason="explicit memory request")
        if any(lowered.startswith(prefix.lower()) for prefix in self._FEEDBACK_PREFIXES):
            return Route(skill="feedback", reason="message starts with feedback keyword")
        return Route(skill="chat", reason="default conversational route")
