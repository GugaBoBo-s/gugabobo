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

    # all three read-only tools are min_skill=chat, so a plain user gets them
    assert names == {"get_current_time", "recall_messages", "search_memory"}


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
