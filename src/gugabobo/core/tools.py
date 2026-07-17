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
    # Injected clients for owner tools. Optional so read-only tools and tests
    # need not provide them; owner tools create a default if absent.
    napcat_client: object | None = None
    github_client: object | None = None
    # Optional injected web-search callable (query -> formatted string) for
    # tests; falls back to the real Serper client when absent.
    web_search: Callable[[str], str] | None = None
    # Optional injected read-url callable (url -> text) for tests; falls back
    # to the real WebReaderClient when absent.
    read_url: Callable[[str], str] | None = None


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


def _get_napcat(context: ToolContext):
    if context.napcat_client is not None:
        return context.napcat_client
    from gugabobo.infra.napcat_client import NapCatClient

    return NapCatClient()


def _get_github(context: ToolContext):
    if context.github_client is not None:
        return context.github_client
    from gugabobo.infra.github_client import GitHubClient

    return GitHubClient()


def _tool_send_qq_message(context: ToolContext, args: dict[str, object]) -> str:
    target = str(args.get("target", "") or "").strip()
    content = str(args.get("content", "") or "").strip()
    if not target or not content:
        return "错误：target 和 content 都不能为空。"
    client = _get_napcat(context)

    # Resolve recipient: pure digits = QQ id, otherwise look up by remark/nickname.
    if target.isdigit():
        recipient_id, label = target, target
    else:
        try:
            matches = client.find_friends(target)
        except Exception as exc:
            return f"查找好友「{target}」出错：{exc}。可以直接给我 QQ 号。"
        if not matches:
            return f"没有在好友里找到「{target}」。可以直接给我对方的 QQ 号。"
        if len(matches) > 1:
            lines = "\n".join(
                f"- {f.get('remark') or f.get('nickname')}（QQ {f.get('user_id')}）"
                for f in matches
            )
            return f"「{target}」匹配到多个联系人，请指定 QQ 号：\n{lines}"
        friend = matches[0]
        recipient_id = str(friend.get("user_id"))
        label = str(friend.get("remark") or friend.get("nickname") or recipient_id)

    try:
        client.send_private_msg(recipient_id, content)
    except Exception as exc:
        context.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="tool.send_qq_message",
            target=f"qq:{recipient_id}",
            status="failed",
            risk_level="high",
            detail=str(exc)[:200],
        )
        return f"发送给 {label}（QQ {recipient_id}）失败：{exc}"
    context.store.add_audit_log(
        actor_source=context.source,
        actor_user_id=context.user_id,
        action="tool.send_qq_message",
        target=f"qq:{recipient_id}",
        status="ok",
        risk_level="high",
        detail=content[:200],
    )
    return f"已发送给 {label}（QQ {recipient_id}）：{content}"


def _tool_github_read(context: ToolContext, args: dict[str, object]) -> str:
    action = str(args.get("action", "") or "").strip()
    client = _get_github(context)
    if not getattr(client, "configured", False):
        return "错误：GitHub 未配置（缺少 token）。"
    try:
        if action == "get_pull_request":
            number = int(args.get("number", 0))
            if number <= 0:
                return "错误：get_pull_request 需要 number。"
            pr = client.get_pull_request(number)
            head = pr.get("head", {})
            sha = head.get("sha", "") if isinstance(head, dict) else ""
            checks = ""
            if sha:
                try:
                    checks = client.get_checks_status(sha)
                except Exception:
                    checks = "unknown"
            return (
                f"PR #{pr.get('number')} [{pr.get('state')}"
                f"{'/merged' if pr.get('merged') else ''}] {pr.get('title')}\n"
                f"作者：{(pr.get('user') or {}).get('login', '?')}  检查：{checks or 'n/a'}\n"
                f"{pr.get('html_url', '')}"
            )
        if action == "list_pull_requests":
            state = str(args.get("state", "open") or "open")
            prs = client.list_pull_requests(state=state)
            if not prs:
                return f"没有 {state} 状态的 PR。"
            return "\n".join(
                f"#{p.get('number')} [{p.get('state')}] {p.get('title')}" for p in prs[:20]
            )
        if action == "list_issues":
            state = str(args.get("state", "open") or "open")
            issues = client.list_issues(state=state, limit=20)
            # GitHub returns PRs in the issues endpoint too; filter them out.
            issues = [i for i in issues if "pull_request" not in i]
            if not issues:
                return f"没有 {state} 状态的 issue。"
            return "\n".join(
                f"#{i.get('number')} [{i.get('state')}] {i.get('title')}" for i in issues[:20]
            )
        return (
            "错误：未知 action。支持：get_pull_request(number) / "
            "list_pull_requests(state) / list_issues(state)。"
        )
    except Exception as exc:
        return f"GitHub 查询失败：{exc}"


def _tool_list_conversations(context: ToolContext, args: dict[str, object]) -> str:
    limit = _clamp_limit(args.get("limit"), default=15, maximum=50)
    rows = context.store.list_conversations(limit=limit)
    if not rows:
        return "还没有任何会话记录。"
    return "\n".join(
        f"{row['conversation_id']}：{row['message_count']} 条，最后活跃 {row['last_message_at']}"
        for row in rows
    )


def _tool_web_search(context: ToolContext, args: dict[str, object]) -> str:
    query = str(args.get("query", "") or "").strip()
    if not query:
        return "错误：query 不能为空。"
    if context.web_search is not None:
        return context.web_search(query)
    from gugabobo.infra.web_search import run_web_search

    return run_web_search(query)


def _tool_read_url(context: ToolContext, args: dict[str, object]) -> str:
    url = str(args.get("url", "") or "").strip()
    if not url:
        return "错误：url 不能为空。"
    if context.read_url is not None:
        return context.read_url(url)
    from gugabobo.infra.web_reader import run_read_url

    return run_read_url(url)


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
        Tool(
            name="send_qq_message",
            description=(
                "主动通过 QQ 给指定联系人发送一条私聊消息。当主人要你给某人发消息、"
                "转告、通知时使用（例如『用QQ给kc说明天开会』『告诉老王我到了』）。"
                "target 可以是好友备注/昵称，也可以是纯数字 QQ 号；内容里不要带敏感信息。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "收件人：好友备注/昵称，或纯数字 QQ 号。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要发送的消息正文。",
                    },
                },
                "required": ["target", "content"],
            },
            handler=_tool_send_qq_message,
            min_skill="owner_action",
        ),
        Tool(
            name="github_read",
            description=(
                "查询 GitHub 仓库的 PR / issue / CI 状态（只读）。当主人问某个 PR 合了没、"
                "CI 过了没、有哪些开放的 PR 或 issue 时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_pull_request", "list_pull_requests", "list_issues"],
                        "description": "查询类型。",
                    },
                    "number": {
                        "type": "integer",
                        "description": "PR 编号，get_pull_request 时必填。",
                    },
                    "state": {
                        "type": "string",
                        "description": "列表查询的状态过滤：open/closed/all，默认 open。",
                    },
                },
                "required": ["action"],
            },
            handler=_tool_github_read,
            min_skill="owner_action",
        ),
        Tool(
            name="list_conversations",
            description=(
                "列出最近活跃的会话概览（每个会话的消息数和最后活跃时间）。"
                "当主人问『我最近都在忙什么』『哪些群/对话比较活跃』时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回会话数，默认 15，最多 50。",
                    }
                },
            },
            handler=_tool_list_conversations,
            min_skill="owner_action",
        ),
        Tool(
            name="web_search",
            description=(
                "联网搜索，获取实时/最新的外部信息。当问题涉及时事、最新版本、"
                "价格、文档、你不确定或训练数据里可能过时的事实时使用；"
                "不要用它回答闲聊或你已经确定知道的常识。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或问题，尽量具体。",
                    }
                },
                "required": ["query"],
            },
            handler=_tool_web_search,
            min_skill="chat",
        ),
        Tool(
            name="read_url",
            description=(
                "读取一个网页链接的正文内容。当用户发来一个网址问『这篇讲了啥』，"
                "或 web_search 的摘要不够、需要看某个结果的全文时使用。"
                "只接受 http/https 完整链接。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要读取的完整网址（http:// 或 https:// 开头）。",
                    }
                },
                "required": ["url"],
            },
            handler=_tool_read_url,
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
