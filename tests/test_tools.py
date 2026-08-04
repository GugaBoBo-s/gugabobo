from __future__ import annotations

from gugabobo.config import get_settings
from gugabobo.core.persona import Persona
from gugabobo.core.tools import (
    Tool,
    ToolContext,
    ToolRegistry,
)
from gugabobo.infra.llm import AgentResult
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill


def _store_with_history(tmp_path):
    store = MemoryStore(tmp_path / "tools.db")
    store.add_message(
        source="telegram_private",
        user_id="u1",
        role="user",
        content="我喜欢喝美式咖啡",
        conversation_id="telegram:user:u1",
    )
    store.add_message(
        source="telegram_private",
        user_id="gugabobo",
        role="assistant",
        content="记住啦",
        conversation_id="telegram:user:u1",
    )
    return store


# ── individual tool behaviour ──────────────────────────────────────────────
def test_current_time_tool_returns_beijing_time(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="c", access_role="user")
    registry = ToolRegistry()

    out = registry.dispatch("get_current_time", "{}", ctx)

    assert "北京时间" in out
    # year prefix sanity — output starts with a 4-digit year
    assert out[:2] == "20"


def test_recall_messages_tool_reads_conversation(tmp_path):
    store = _store_with_history(tmp_path)
    ctx = ToolContext(store=store, conversation_id="telegram:user:u1", access_role="user")
    registry = ToolRegistry()

    out = registry.dispatch("recall_messages", '{"limit": 10}', ctx)

    assert "美式咖啡" in out
    assert "用户" in out


def test_recall_messages_tool_empty_conversation(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="telegram:user:none", access_role="user")
    registry = ToolRegistry()

    out = registry.dispatch("recall_messages", "{}", ctx)

    assert out == "本会话没有历史消息。"


def test_search_memory_tool_filters_by_query(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    store.add_memory_item(
        subject="telegram:user:u1",
        content="用户喜欢蓝色",
        memory_type="preference",
        importance=8,
    )
    store.add_memory_item(
        subject="telegram:user:u1",
        content="用户住在上海",
        memory_type="fact",
        importance=6,
    )
    ctx = ToolContext(store=store, conversation_id="telegram:user:u1", access_role="user")
    registry = ToolRegistry()

    hit = registry.dispatch("search_memory", '{"query": "蓝色"}', ctx)
    miss = registry.dispatch("search_memory", '{"query": "不存在的词"}', ctx)

    assert "蓝色" in hit
    assert "上海" not in hit
    assert miss == "没有找到相关的长期记忆。"


# ── write tools: write_memory + record_feedback ────────────────────────────
def _write_ctx(store, role="trusted"):
    return ToolContext(
        store=store,
        conversation_id="telegram:user:u1",
        access_role=role,
        source="telegram_private",
        user_id="u1",
    )


def test_write_memory_tool_persists_and_audits(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "write_memory",
        '{"content": "用户是后端工程师", "memory_type": "identity", "importance": 8}',
        _write_ctx(store),
    )

    assert "已记住" in out
    items = store.list_memory_items(subject="telegram:user:u1")
    assert items[0]["content"] == "用户是后端工程师"
    assert items[0]["source"] == "agent_tool"
    # audit trail recorded
    logs = store.list_audit_logs(limit=10)
    assert any(log["action"] == "tool.write_memory" for log in logs)


def test_write_memory_tool_rejects_secrets(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "write_memory",
        '{"content": "我的 API key 是 sk-abc123"}',
        _write_ctx(store),
    )

    assert "拒绝" in out
    assert store.list_memory_items(subject="telegram:user:u1") == []


def test_write_memory_tool_rejects_empty_content(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch("write_memory", '{"content": "   "}', _write_ctx(store))

    assert "不能为空" in out
    assert store.list_memory_items(subject="telegram:user:u1") == []


def test_record_feedback_tool_persists_and_audits(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "record_feedback",
        '{"content": "回复太啰嗦了"}',
        _write_ctx(store),
    )

    assert "已记录反馈" in out
    feedbacks = store.list_feedbacks(limit=10)
    assert feedbacks[0]["content"] == "回复太啰嗦了"
    assert feedbacks[0]["source"] == "telegram_private"
    logs = store.list_audit_logs(limit=10)
    assert any(log["action"] == "tool.record_feedback" for log in logs)


def test_write_tools_hidden_from_user_role(tmp_path):
    registry = ToolRegistry()

    user_names = {spec["function"]["name"] for spec in registry.specs_for("user")}
    trusted_names = {spec["function"]["name"] for spec in registry.specs_for("trusted")}

    # plain user only sees read-only tools
    assert "write_memory" not in user_names
    assert "record_feedback" not in user_names
    # trusted (and owner) get the write tools
    assert "write_memory" in trusted_names
    assert "record_feedback" in trusted_names


def test_write_memory_denied_for_user_role_at_dispatch(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "write_memory",
        '{"content": "不该被记录"}',
        _write_ctx(store, role="user"),
    )

    assert "不能使用工具" in out
    assert store.list_memory_items(subject="telegram:user:u1") == []


# ── registry access control ────────────────────────────────────────────────
def test_registry_dispatch_rejects_unknown_tool(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="c", access_role="user")
    registry = ToolRegistry()

    out = registry.dispatch("does_not_exist", "{}", ctx)

    assert "未知工具" in out


def test_registry_dispatch_handles_bad_json(tmp_path):
    store = _store_with_history(tmp_path)
    ctx = ToolContext(store=store, conversation_id="telegram:user:u1", access_role="user")
    registry = ToolRegistry()

    # malformed arguments must not crash — falls back to empty args (default limit)
    out = registry.dispatch("recall_messages", "{not valid json", ctx)

    assert "美式咖啡" in out


def test_registry_specs_available_to_user_role(tmp_path):
    registry = ToolRegistry()

    specs = registry.specs_for("user")
    names = {spec["function"]["name"] for spec in specs}

    # read-only + web_search + read_url are min_skill=chat, so a plain user gets them
    assert names == {
        "get_current_time",
        "recall_messages",
        "search_memory",
        "web_search",
            "read_url",
            "remote_skill",
            "read_x_posts",
            "read_agent_guidance",
            "steam_lookup",
        }


def test_registry_blocked_tool_denied_at_dispatch(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="c", access_role="user")
    owner_only = Tool(
        name="danger",
        description="owner only",
        parameters={"type": "object", "properties": {}},
        handler=lambda c, a: "should not run",
        min_skill="feedback",  # user cannot use feedback skill
    )
    registry = ToolRegistry(tools=[owner_only])

    out = registry.dispatch("danger", "{}", ctx)

    assert "不能使用工具" in out


def test_chat_skill_delegates_tools_to_pydantic_runtime():
    class CapturingRuntime:
        configured = True

        def __init__(self):
            self.kwargs = {}

        def run(self, text, **kwargs):
            self.kwargs = kwargs
            return AgentResult(f"reply: {text}", "test")

    runtime = CapturingRuntime()
    skill = ChatSkill(Persona(), llm_client=runtime)
    tools = [{"type": "function", "function": {"name": "get_current_time"}}]

    def dispatch(name, args):
        return "时间结果"

    reply = skill.reply("现在几点", tool_specs=tools, dispatch=dispatch)

    assert reply == "reply: 现在几点"
    assert runtime.kwargs["tool_specs"] == tools
    assert runtime.kwargs["dispatch"] is dispatch


# ── owner tools: outbound messaging / github_read / list_conversations ──────
class FakeNapCat:
    def __init__(self, friends=None, fail=False):
        self._friends = friends or []
        self.fail = fail
        self.sent = []

    def find_friends(self, target):
        return list(self._friends)

    def send_private_msg(self, user_id, message):
        if self.fail:
            raise RuntimeError("network down")
        self.sent.append((str(user_id), message))


class FakeGitHub:
    configured = True

    def __init__(self):
        self.prs = {21: {"number": 21, "state": "closed", "merged": True,
                         "title": "add tools", "user": {"login": "GuGabobo"},
                         "head": {"sha": "abc123"}, "html_url": "http://x/21"}}

    def get_pull_request(self, number):
        return self.prs[number]

    def get_checks_status(self, sha):
        return "success"

    def list_pull_requests(self, state="open"):
        return [] if state == "open" else [self.prs[21]]

    def list_issues(self, state="open", limit=20):
        return [{"number": 5, "state": "open", "title": "a bug"}]


def _owner_ctx(store, **kw):
    return ToolContext(
        store=store, conversation_id="telegram:user:owner", access_role="owner",
        source="telegram_private", user_id="owner", **kw
    )


def test_send_qq_message_by_numeric_id(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    napcat = FakeNapCat()
    registry = ToolRegistry()

    out = registry.dispatch(
        "send_qq_message", '{"target": "12345", "content": "你好"}',
        _owner_ctx(store, napcat_client=napcat),
    )

    assert "已发送" in out
    assert napcat.sent == [("12345", "你好")]
    assert any(log["action"] == "tool.send_qq_message" for log in store.list_audit_logs(limit=5))


def test_send_qq_message_resolves_friend_by_name(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    napcat = FakeNapCat(friends=[{"user_id": 999, "remark": "kc", "nickname": "K"}])
    registry = ToolRegistry()

    out = registry.dispatch(
        "send_qq_message", '{"target": "kc", "content": "明天开会"}',
        _owner_ctx(store, napcat_client=napcat),
    )

    assert "已发送" in out and "kc" in out
    assert napcat.sent == [("999", "明天开会")]


def test_send_qq_message_ambiguous_friend(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    napcat = FakeNapCat(friends=[
        {"user_id": 1, "remark": "kc", "nickname": "K"},
        {"user_id": 2, "remark": "kc2", "nickname": "K2"},
    ])
    registry = ToolRegistry()

    out = registry.dispatch(
        "send_qq_message", '{"target": "kc", "content": "hi"}',
        _owner_ctx(store, napcat_client=napcat),
    )

    assert "多个" in out
    assert napcat.sent == []


def test_send_qq_message_denied_for_non_owner(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    napcat = FakeNapCat()
    registry = ToolRegistry()

    ctx = ToolContext(store=store, conversation_id="c", access_role="trusted",
                      source="s", user_id="u", napcat_client=napcat)
    out = registry.dispatch("send_qq_message", '{"target": "1", "content": "x"}', ctx)

    assert "不能使用工具" in out
    assert napcat.sent == []


def test_send_telegram_message_queues_async_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "1234567890:" + "A" * 35)
    get_settings.cache_clear()
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "send_telegram_message",
        '{"target": "-100123456", "content": "部署完成"}',
        _owner_ctx(store),
    )

    notification = store.list_owner_notifications()[0]
    assert "已加入 Telegram 发送队列" in out
    assert notification["event_type"] == "agent_telegram_message"
    assert notification["platform"] == "telegram"
    assert notification["recipient_id"] == "-100123456"
    assert notification["content"] == "部署完成"
    assert notification["status"] == "pending"
    audit = store.list_audit_logs(limit=1)[0]
    assert audit["action"] == "tool.send_telegram_message"
    assert audit["status"] == "queued"


def test_send_telegram_message_validates_target_and_configuration(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    missing_token = registry.dispatch(
        "send_telegram_message",
        '{"target": "@valid_channel", "content": "hello"}',
        _owner_ctx(store),
    )
    invalid_target = registry.dispatch(
        "send_telegram_message",
        '{"target": "not a chat", "content": "hello"}',
        _owner_ctx(store),
    )

    assert "Token 未配置" in missing_token
    assert "target 必须" in invalid_target
    assert store.list_owner_notifications() == []


def test_github_read_get_pull_request(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "github_read", '{"action": "get_pull_request", "number": 21}',
        _owner_ctx(store, github_client=FakeGitHub()),
    )

    assert "#21" in out and "merged" in out and "success" in out


def test_github_read_list_issues_filters_prs(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    registry = ToolRegistry()

    out = registry.dispatch(
        "github_read", '{"action": "list_issues"}',
        _owner_ctx(store, github_client=FakeGitHub()),
    )

    assert "#5" in out and "a bug" in out


def test_github_read_owner_only(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="c", access_role="user",
                      source="s", user_id="u")
    registry = ToolRegistry()

    out = registry.dispatch("github_read", '{"action": "list_issues"}', ctx)

    assert "不能使用工具" in out


def test_list_conversations_tool(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    store.add_message(source="telegram_private", user_id="u1", role="user",
                      content="hi", conversation_id="telegram:user:u1")
    registry = ToolRegistry()

    out = registry.dispatch("list_conversations", "{}", _owner_ctx(store))

    assert "telegram:user:u1" in out


def test_owner_tools_hidden_from_user_and_trusted(tmp_path):
    registry = ToolRegistry()
    user_names = {s["function"]["name"] for s in registry.specs_for("user")}
    trusted_names = {s["function"]["name"] for s in registry.specs_for("trusted")}
    owner_names = {s["function"]["name"] for s in registry.specs_for("owner")}

    for tool in (
        "send_qq_message",
        "send_telegram_message",
        "github_read",
        "list_conversations",
        "send_file_with_glitter",
        "edit_agent_guidance",
    ):
        assert tool not in user_names
        assert tool not in trusted_names
        assert tool in owner_names


def test_glitter_tool_uses_owner_scoped_sender_and_audits(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    calls = []
    ctx = ToolContext(
        store=store,
        conversation_id="c",
        access_role="owner",
        source="telegram_private",
        user_id="owner",
        glitter_send=lambda peer, path: calls.append((peer, path)) or "发送完成",
    )

    out = ToolRegistry().dispatch(
        "send_file_with_glitter",
        '{"peer":"laptop","path":"report.txt"}',
        ctx,
    )

    assert out == "发送完成"
    assert calls == [("laptop", "report.txt")]
    assert any(log["action"] == "tool.glitter.send" for log in store.list_audit_logs())


def test_remote_skill_tool_uses_fixed_reader(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    calls = []
    ctx = ToolContext(
        store=store,
        conversation_id="c",
        access_role="user",
        remote_skills=lambda action, skill, resource: calls.append(
            (action, skill, resource)
        )
        or "skill content",
    )

    out = ToolRegistry().dispatch(
        "remote_skill",
        '{"action":"read","skill":"ux-writing"}',
        ctx,
    )

    assert out == "skill content"
    assert calls == [("read", "ux-writing", "SKILL.md")]


def test_x_reader_tool_uses_allowlisted_account(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    calls = []
    ctx = ToolContext(
        store=store,
        conversation_id="c",
        access_role="user",
        x_read=lambda account: calls.append(account) or "posts",
    )

    out = ToolRegistry().dispatch(
        "read_x_posts",
        '{"account":"ScarletKc_"}',
        ctx,
    )

    assert out == "posts"
    assert calls == ["ScarletKc_"]


def test_owner_can_edit_fixed_prompt_guidance_document(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    calls = []
    ctx = ToolContext(
        store=store,
        conversation_id="c",
        access_role="owner",
        source="telegram_private",
        user_id="owner",
        prompt_guidance=lambda action, name, content: calls.append(
            (action, name, content)
        )
        or "updated",
    )

    out = ToolRegistry().dispatch(
        "edit_agent_guidance",
        '{"name":"soul.md","content":"new soul"}',
        ctx,
    )

    assert out == "updated"
    assert calls == [("replace", "soul.md", "new soul")]
    assert any(
        log["action"] == "tool.prompt_guidance.replace" for log in store.list_audit_logs()
    )


def test_steam_lookup_is_read_only_and_available_to_every_role(tmp_path):
    registry = ToolRegistry()
    for role in ("user", "trusted", "owner"):
        names = {item["function"]["name"] for item in registry.specs_for(role)}
        assert "steam_lookup" in names

    calls = []
    ctx = ToolContext(
        store=MemoryStore(tmp_path / "steam.db"),
        conversation_id="c",
        access_role="user",
        steam_lookup=lambda action, query, app_id: calls.append((action, query, app_id))
        or "Steam result",
    )
    out = registry.dispatch(
        "steam_lookup",
        '{"action":"details","app_id":570}',
        ctx,
    )

    assert out == "Steam result"
    assert calls == [("details", "", 570)]


# ── web_search tool ─────────────────────────────────────────────────────────
def test_web_search_tool_uses_injected_callable(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    calls = []

    def fake_search(query):
        calls.append(query)
        return "1. 结果标题\n摘要内容\nhttp://example.com"

    ctx = ToolContext(
        store=store, conversation_id="c", access_role="user",
        source="s", user_id="u", web_search=fake_search,
    )
    registry = ToolRegistry()

    out = registry.dispatch("web_search", '{"query": "gpt-5 发布了吗"}', ctx)

    assert calls == ["gpt-5 发布了吗"]
    assert "结果标题" in out


def test_web_search_tool_rejects_empty_query(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="c", access_role="user",
                      web_search=lambda q: "should not run")
    registry = ToolRegistry()

    out = registry.dispatch("web_search", '{"query": "  "}', ctx)

    assert "不能为空" in out


def test_web_search_available_to_all_roles(tmp_path):
    registry = ToolRegistry()
    for role in ("user", "trusted", "owner"):
        names = {s["function"]["name"] for s in registry.specs_for(role)}
        assert "web_search" in names


# ── read_url tool ────────────────────────────────────────────────────────────
def test_read_url_tool_uses_injected_callable(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    calls = []

    def fake_reader(url):
        calls.append(url)
        return "标题：示例\n\n这是正文内容。"

    ctx = ToolContext(
        store=store, conversation_id="c", access_role="user",
        source="s", user_id="u", read_url=fake_reader,
    )
    registry = ToolRegistry()

    out = registry.dispatch("read_url", '{"url": "https://example.com/x"}', ctx)

    assert calls == ["https://example.com/x"]
    assert "正文内容" in out


def test_read_url_tool_rejects_empty(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    ctx = ToolContext(store=store, conversation_id="c", access_role="user",
                      read_url=lambda u: "should not run")
    registry = ToolRegistry()

    out = registry.dispatch("read_url", '{"url": "  "}', ctx)

    assert "不能为空" in out


def test_read_url_available_to_all_roles(tmp_path):
    registry = ToolRegistry()
    for role in ("user", "trusted", "owner"):
        names = {s["function"]["name"] for s in registry.specs_for(role)}
        assert "read_url" in names
