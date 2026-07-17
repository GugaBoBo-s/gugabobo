from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Callable

from gugabobo.core.access import role_can_use_skill
from gugabobo.memory.store import MemoryStore


# Beijing time — the bot's operators and users are China-based, so tool output
# defaults to this rather than server UTC.
_BEIJING = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool needs to run, scoped to the current turn."""

    store: MemoryStore
    conversation_id: str
    access_role: str
    # Who is talking, for feedback attribution and audit trails. Defaults keep
    # older callers/tests that only pass the first three fields working.
    source: str = "unknown"
    user_id: str = "unknown"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, object]
    handler: Callable[[ToolContext, dict[str, object]], str]
    # Minimum skill this tool maps to for access control. Reuses the same
    # owner/trusted/user tiering as the rest of the agent (see access.py).
    min_skill: str = "chat"

    def spec(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _clamp_limit(raw: object, default: int = 10, maximum: int = 50) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, value))


def _tool_current_time(context: ToolContext, args: dict[str, object]) -> str:
    now = datetime.now(_BEIJING)
    return now.strftime("%Y-%m-%d %H:%M:%S (北京时间, 周%w)")


def _tool_recall_messages(context: ToolContext, args: dict[str, object]) -> str:
    limit = _clamp_limit(args.get("limit"), default=10, maximum=50)
    rows = context.store.list_conversation_messages(context.conversation_id, limit=limit)
    if not rows:
        return "本会话没有历史消息。"
    lines = []
    for row in rows:
        who = "用户" if row["role"] == "user" else "咕嘎BoBo"
        lines.append(f"[{row['created_at']}] {who}: {row['content']}")
    return "\n".join(lines)


def _tool_search_memory(context: ToolContext, args: dict[str, object]) -> str:
    limit = _clamp_limit(args.get("limit"), default=10, maximum=50)
    query = str(args.get("query", "") or "").strip()
    items = context.store.list_memory_items(subject=context.conversation_id, limit=50)
    if query:
        lowered = query.lower()
        items = [item for item in items if lowered in str(item["content"]).lower()]
    items = items[:limit]
    if not items:
        return "没有找到相关的长期记忆。" if query else "还没有记录任何长期记忆。"
    lines = [
        f"#{item['id']} [{item['memory_type']}; 重要度={item['importance']}] {item['content']}"
        for item in items
    ]
    return "\n".join(lines)


def _clamp_importance(raw: object, default: int = 6) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, value))


# Content the agent must never persist to long-term memory (mirrors the
# persona's memory-safety rules). Kept deliberately small and obvious.
_SECRET_HINTS = (
    "api key",
    "apikey",
    "token",
    "password",
    "密码",
    "密钥",
    "身份证",
    "银行卡",
    "信用卡",
)


def _tool_write_memory(context: ToolContext, args: dict[str, object]) -> str:
    content = str(args.get("content", "") or "").strip()
    if not content:
        return "错误：memory content 不能为空。"
    lowered = content.lower()
    if any(hint in lowered for hint in _SECRET_HINTS):
        return "错误：拒绝记录疑似敏感信息（密钥/密码/证件/银行卡等）。"
    memory_type = str(args.get("memory_type", "") or "note").strip() or "note"
    importance = _clamp_importance(args.get("importance"))
    memory_id = context.store.add_memory_item(
        subject=context.conversation_id,
        content=content,
        memory_type=memory_type,
        importance=importance,
        source="agent_tool",
    )
    context.store.add_audit_log(
        actor_source=context.source,
        actor_user_id=context.user_id,
        action="tool.write_memory",
        target=f"memory:{memory_id}",
        detail=content[:200],
    )
    return f"已记住（记忆 #{memory_id}，重要度 {importance}）：{content}"


def _tool_record_feedback(context: ToolContext, args: dict[str, object]) -> str:
    content = str(args.get("content", "") or "").strip()
    if not content:
        return "错误：feedback content 不能为空。"
    feedback_id = context.store.add_feedback(
        source=context.source,
        user_id=context.user_id,
        content=content,
    )
    context.store.add_audit_log(
        actor_source=context.source,
        actor_user_id=context.user_id,
        action="tool.record_feedback",
        target=f"feedback:{feedback_id}",
        detail=content[:200],
    )
    return f"已记录反馈 #{feedback_id}：{content}"


def default_tools() -> list[Tool]:
    return [
        Tool(
            name="get_current_time",
            description="获取当前的日期和时间（北京时间）。当用户问现在几点、今天几号、星期几时使用。",
            parameters={"type": "object", "properties": {}},
            handler=_tool_current_time,
            min_skill="chat",
        ),
        Tool(
            name="recall_messages",
            description=(
                "读取当前会话最近的历史消息。当用户提到之前说过的内容、"
                "问『我刚才说了什么』『我们聊到哪了』时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "要读取的最近消息条数，默认 10，最多 50。",
                    }
                },
            },
            handler=_tool_recall_messages,
            min_skill="chat",
        ),
        Tool(
            name="search_memory",
            description=(
                "查询关于当前用户/会话的长期记忆（偏好、身份、稳定事实）。"
                "当需要回忆用户明确要你记住的信息时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "可选的关键词过滤；留空则返回全部记忆。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数，默认 10，最多 50。",
                    },
                },
            },
            handler=_tool_search_memory,
            min_skill="chat",
        ),
        Tool(
            name="write_memory",
            description=(
                "把关于当前用户的长期事实或偏好写入长期记忆，之后的对话能记住。"
                "当用户透露稳定的偏好、身份、习惯或长期项目事实时主动使用"
                "（例如『我是后端工程师』『我喜欢喝美式』）。"
                "不要记录一次性的闲聊、临时状态，或 API key、密码等敏感信息。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要记住的事实，简短、明确、可解释。",
                    },
                    "memory_type": {
                        "type": "string",
                        "description": "记忆类型，如 preference/identity/fact，默认 fact。",
                    },
                    "importance": {
                        "type": "integer",
                        "description": "重要度 1-10，默认 6。",
                    },
                },
                "required": ["content"],
            },
            handler=_tool_write_memory,
            min_skill="memory",
        ),
        Tool(
            name="record_feedback",
            description=(
                "当用户在吐槽、抱怨、提改进建议或指出 bug 时，把它记进反馈表，"
                "供后续改进。当用户表达不满或建议时主动使用"
                "（例如『你回复太啰嗦了』『这个功能能不能加个X』）。"
                "普通提问、闲聊不要记。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "反馈的核心内容，用一句话概括用户的意见。",
                    }
                },
                "required": ["content"],
            },
            handler=_tool_record_feedback,
            min_skill="feedback",
        ),
    ]


class ToolRegistry:
    """Holds the available tools and dispatches calls, gated by access role."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools = {tool.name: tool for tool in (tools or default_tools())}

    def available_for(self, access_role: str) -> list[Tool]:
        return [
            tool
            for tool in self._tools.values()
            if role_can_use_skill(access_role, tool.min_skill)
        ]

    def specs_for(self, access_role: str) -> list[dict[str, object]]:
        return [tool.spec() for tool in self.available_for(access_role)]

    def dispatch(self, name: str, raw_arguments: str, context: ToolContext) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：未知工具 {name}。"
        if not role_can_use_skill(context.access_role, tool.min_skill):
            return f"错误：当前权限 {context.access_role} 不能使用工具 {name}。"
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
        except (json.JSONDecodeError, TypeError):
            args = {}
        if not isinstance(args, dict):
            args = {}
        try:
            return tool.handler(context, args)
        except Exception as exc:  # tools must never crash the agent loop
            return f"错误：工具 {name} 执行失败：{exc}"
