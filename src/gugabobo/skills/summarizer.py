from __future__ import annotations

from gugabobo.infra.llm import OpenAICompatibleClient
from gugabobo.infra.logs import get_logger

_SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话摘要器。把提供的对话历史压缩成一段简洁的中文摘要，"
    "用于帮助助手记住早期对话内容。"
    "如果已有旧摘要，把它和新对话合并成一段连贯的新摘要，不要丢掉旧摘要里的重要事实。"
    "摘要要点：保留用户的身份、偏好、正在进行的任务、已做出的决定、重要事实和未解决的问题。"
    "丢弃寒暄、口水话和无信息量的内容。只输出摘要正文，不要加标题、前缀或多余解释。"
)


class SummarizerSkill:
    def __init__(self, llm_client: OpenAICompatibleClient) -> None:
        self.llm_client = llm_client

    def summarize(
        self,
        messages: list[dict[str, str]],
        previous_summary: str = "",
    ) -> str | None:
        if not self.llm_client.configured or not messages:
            return None
        transcript = "\n".join(
            f"{'用户' if item['role'] == 'user' else '咕嘎BoBo'}: {item['content']}"
            for item in messages
        )
        parts = []
        if previous_summary.strip():
            parts.append(f"已有摘要：\n{previous_summary.strip()}")
        parts.append(f"新增对话：\n{transcript}")
        user_content = "\n\n".join(parts)
        try:
            summary = self.llm_client.complete(
                [
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ]
            )
        except Exception as exc:
            get_logger().warning("summary generation failed: %s", exc)
            return None
        summary = summary.strip()
        return summary or None
