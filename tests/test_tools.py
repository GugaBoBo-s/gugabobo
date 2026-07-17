from __future__ import annotations

from gugabobo.core.persona import Persona
from gugabobo.core.tools import (
    Tool,
    ToolContext,
    ToolRegistry,
)
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

    # read-only + web_search are min_skill=chat, so a plain user gets them
    assert names == {"get_current_time", "recall_messages", "search_memory", "web_search"}


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


# ── full tool-calling loop through ChatSkill with a scripted fake client ────
class ScriptedToolClient:
    """Fake LLM client that returns a scripted sequence of tool-call / content
    responses so the loop can be tested without a real relay or token spend."""

    configured = True

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0
        self.dispatched = []

    def build_messages(self, text, persona, history, system_context, images):
        return [{"role": "user", "content": text}]

    def complete_messages(self, messages, tools=None, temperature=0.7):
        step = self._script[self.calls]
        self.calls += 1
        return step


class _Result:
    def __init__(self, content="", tool_calls=None, message=None):
        self.content = content
        self.tool_calls = tool_calls
        self.message = message


def test_chat_skill_runs_tool_loop_then_answers():
    # round 1: model asks for get_current_time; round 2: model answers with text
    tool_call = {"id": "call_1", "function": {"name": "get_current_time", "arguments": "{}"}}
    script = [
        _Result(tool_calls=[tool_call], message={"role": "assistant", "tool_calls": [tool_call]}),
        _Result(content="现在是下午三点。"),
    ]
    client = ScriptedToolClient(script)
    skill = ChatSkill(Persona(), llm_client=client)

    dispatched = []

    def dispatch(name, arguments):
        dispatched.append((name, arguments))
        return "2026-07-17 15:00:00 (北京时间, 周4)"

    reply = skill.reply(
        "现在几点",
        tool_specs=[{"type": "function", "function": {"name": "get_current_time"}}],
        dispatch=dispatch,
    )

    assert reply == "现在是下午三点。"
    assert dispatched == [("get_current_time", "{}")]
    assert client.calls == 2


def test_chat_skill_tool_loop_hits_round_cap_and_forces_answer():
    # model keeps asking for tools forever; loop must cap and force a final answer
    tool_call = {"id": "c", "function": {"name": "get_current_time", "arguments": "{}"}}
    looping = _Result(
        tool_calls=[tool_call], message={"role": "assistant", "tool_calls": [tool_call]}
    )
    # 5 loop rounds + 1 forced final call (no tools) that finally returns content
    script = [looping] * 5 + [_Result(content="兜底回答。")]
    client = ScriptedToolClient(script)
    skill = ChatSkill(Persona(), llm_client=client)

    reply = skill.reply(
        "现在几点",
        tool_specs=[{"type": "function", "function": {"name": "get_current_time"}}],
        dispatch=lambda name, args: "时间结果",
    )

    assert reply == "兜底回答。"
    # 5 in-loop rounds + 1 final forced call
    assert client.calls == 6


def test_chat_skill_without_tools_uses_plain_path():
    class PlainClient:
        configured = True

        def chat(self, text, persona, history=None, system_context=None, images=None):
            return type("R", (), {"content": f"plain: {text}"})()

    skill = ChatSkill(Persona(), llm_client=PlainClient())

    reply = skill.reply("你好")

    assert reply == "plain: 你好"


# ── owner tools: send_qq_message / github_read / list_conversations ─────────
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

    for tool in ("send_qq_message", "github_read", "list_conversations"):
        assert tool not in user_names
        assert tool not in trusted_names
        assert tool in owner_names


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
