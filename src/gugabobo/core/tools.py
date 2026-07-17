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
