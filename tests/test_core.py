from gugabobo.core.agent import CoreAgent
from gugabobo.core.channel import ChannelContext
from gugabobo.core.persona import Persona
from gugabobo.config import get_settings
from gugabobo.infra.llm import DeepSeekClient, MoonshotClient, OpenAIClient, build_llm_client
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill
from gugabobo.skills.summarizer import SummarizerSkill


def test_chat_records_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    reply = agent.handle_message("你好", source="test", user_id="u1")

    assert "已收到" in reply
    assert agent.store.count_messages() == 2
    get_settings.cache_clear()


def test_feedback_route_records_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    reply = agent.handle_message("建议回复短一点", source="cli", user_id="u1")

    assert "已记录反馈" in reply
    assert agent.store.count_feedbacks() == 1
    get_settings.cache_clear()


def test_explicit_memory_request_records_long_term_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    reply = agent.handle_context_message(
        "记住我喜欢蓝色",
        ChannelContext(
            platform="qq",
            channel_type="private",
            source="qq_private",
            user_id="u1",
            conversation_id="qq:user:u1",
            is_wake_triggered=True,
            metadata={"access_role": "trusted"},
        ),
    )
    memories = agent.store.list_memory_items(subject="qq:user:u1")

    assert "已记住" in reply
    assert memories[0]["content"] == "我喜欢蓝色"
    assert memories[0]["source"] == "explicit_user_request"
    get_settings.cache_clear()


def test_user_role_cannot_write_long_term_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    reply = agent.handle_context_message(
        "记住我喜欢蓝色",
        ChannelContext(
            platform="qq",
            channel_type="private",
            source="qq_private",
            user_id="u1",
            conversation_id="qq:user:u1",
            is_wake_triggered=True,
            metadata={"access_role": "user"},
        ),
    )

    assert "不能写入长期记忆" in reply
    assert agent.store.list_memory_items(subject="qq:user:u1") == []
    get_settings.cache_clear()


def test_regular_chat_does_not_record_long_term_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    agent.handle_message(
        "我喜欢蓝色",
        source="qq_private",
        user_id="u1",
        conversation_id="qq:user:u1",
    )

    assert agent.store.list_memory_items(subject="qq:user:u1") == []
    get_settings.cache_clear()


class FakeLLMClient:
    configured = True

    def chat(self, text, persona, history=None, system_context=None, images=None):
        return type("Result", (), {"content": f"kimi reply: {text}", "model": "kimi-k2.6"})()


class HistoryCapturingLLMClient:
    configured = True

    def __init__(self):
        self.histories = []
        self.system_contexts = []
        self.images = []

    def chat(self, text, persona, history=None, system_context=None, images=None):
        self.histories.append(history or [])
        self.system_contexts.append(system_context or [])
        self.images.append(images or [])
        return type("Result", (), {"content": f"reply: {text}", "model": "test-model"})()


class DisabledLLMClient:
    configured = False


def test_chat_skill_uses_llm_when_configured():
    skill = ChatSkill(Persona(), llm_client=FakeLLMClient())

    reply = skill.reply("你好")

    assert reply == "kimi reply: 你好"


def test_agent_uses_separate_conversation_contexts(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_LLM_CONTEXT_MESSAGES", "10")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))
    llm_client = HistoryCapturingLLMClient()
    agent.chat_skill = ChatSkill(Persona(), llm_client=llm_client)

    agent.handle_message("我是用户A", source="qq_private", user_id="a", conversation_id="qq:user:a")
    agent.handle_message("我是用户B", source="qq_private", user_id="b", conversation_id="qq:user:b")
    agent.handle_message("记得我是谁吗", source="qq_private", user_id="a", conversation_id="qq:user:a")

    third_history = llm_client.histories[2]
    assert any(item["content"] == "我是用户A" for item in third_history)
    assert not any(item["content"] == "我是用户B" for item in third_history)
    get_settings.cache_clear()


def test_agent_accepts_channel_context(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))
    context = ChannelContext(
        platform="telegram",
        channel_type="private",
        source="telegram_private",
        user_id="tg-1",
        conversation_id="telegram:user:tg-1",
        chat_id="tg-1",
        is_owner=True,
        is_wake_triggered=True,
    )

    reply = agent.handle_context_message("你好", context)
    messages = agent.store.list_conversation_messages("telegram:user:tg-1")

    assert "已收到" in reply
    assert messages[0]["source"] == "telegram_private"
    assert messages[0]["user_id"] == "tg-1"
    assert messages[1]["conversation_id"] == "telegram:user:tg-1"
    get_settings.cache_clear()


def test_agent_includes_summary_and_memory_in_system_context(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    store = MemoryStore(tmp_path / "test.db")
    store.upsert_conversation_summary("qq:user:a", "用户正在测试上下文。", 10)
    store.add_memory_item(
        subject="qq:user:a",
        content="用户喜欢蓝色。",
        memory_type="preference",
        importance=8,
    )
    agent = CoreAgent(store)
    llm_client = HistoryCapturingLLMClient()
    agent.chat_skill = ChatSkill(Persona(), llm_client=llm_client)

    agent.handle_message("我喜欢什么颜色？", source="qq_private", user_id="a", conversation_id="qq:user:a")

    system_context = "\n".join(llm_client.system_contexts[0])
    assert "用户正在测试上下文" in system_context
    assert "用户喜欢蓝色" in system_context
    get_settings.cache_clear()


def test_chat_skill_falls_back_without_llm():
    skill = ChatSkill(Persona(), llm_client=DisabledLLMClient())

    reply = skill.reply("你好")

    assert "已收到" in reply


def test_persona_system_summary_contains_operating_rules():
    summary = Persona().system_summary()

    assert "咕嘎BoBo" in summary
    assert "QQ群聊" in summary
    assert "长期记忆" in summary
    assert "合并 PR" in summary
    assert "API key" in summary


def test_build_llm_client_uses_deepseek_provider(monkeypatch):
    monkeypatch.setenv("GUGABOBO_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    client = build_llm_client()

    assert isinstance(client, DeepSeekClient)
    assert client.model == "deepseek-v4-flash"
    get_settings.cache_clear()


def test_build_llm_client_defaults_to_moonshot(monkeypatch):
    monkeypatch.setenv("GUGABOBO_LLM_PROVIDER", "moonshot")
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "test-key")
    get_settings.cache_clear()

    client = build_llm_client()

    assert isinstance(client, MoonshotClient)
    assert client.model == "kimi-k2.6"
    get_settings.cache_clear()


def test_build_user_content_plain_text_without_images():
    from gugabobo.infra.llm import _build_user_content

    assert _build_user_content("你好", []) == "你好"


def test_build_user_content_multimodal_with_images():
    from gugabobo.infra.llm import _build_user_content

    content = _build_user_content("看图", ["data:image/png;base64,Zm9v"])

    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "看图"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,Zm9v"},
    }


def test_build_user_content_image_only_omits_empty_text():
    from gugabobo.infra.llm import _build_user_content

    content = _build_user_content("", ["data:image/png;base64,Zm9v"])

    assert isinstance(content, list)
    assert len(content) == 1
    assert content[0]["type"] == "image_url"


def test_build_llm_client_uses_openai_provider(monkeypatch):
    monkeypatch.setenv("GUGABOBO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GUGABOBO_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GUGABOBO_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("GUGABOBO_OPENAI_MODEL", "gpt-5.6")
    get_settings.cache_clear()

    client = build_llm_client()

    assert isinstance(client, OpenAIClient)
    assert client.base_url == "https://api.example.com/v1"
    assert client.model == "gpt-5.6"
    get_settings.cache_clear()


class SummaryCapableLLMClient:
    configured = True

    def __init__(self):
        self.chat_calls = []
        self.complete_calls = []

    def chat(self, text, persona, history=None, system_context=None, images=None):
        self.chat_calls.append({"history": history or [], "system_context": system_context or []})
        return type("Result", (), {"content": f"reply: {text}", "model": "test-model"})()

    def complete(self, messages, temperature=0.3):
        self.complete_calls.append(messages)
        return "滚动摘要：用户与咕嘎BoBo进行了多轮对话。"


def _make_summary_agent(tmp_path):
    store = MemoryStore(tmp_path / "summary.db")
    agent = CoreAgent(store)
    client = SummaryCapableLLMClient()
    agent.chat_skill = ChatSkill(Persona(), llm_client=client)
    agent.summarizer_skill = SummarizerSkill(client)
    return agent, client


def test_summary_not_triggered_below_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    # High token budget: day-to-day chat stays verbatim, never summarized.
    monkeypatch.setenv("GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS", "24000")
    get_settings.cache_clear()
    agent, client = _make_summary_agent(tmp_path)

    for i in range(5):
        agent.handle_message(f"消息{i}", source="qq_private", user_id="a", conversation_id="qq:user:a")

    assert client.complete_calls == []
    assert agent.store.get_conversation_summary("qq:user:a") is None
    get_settings.cache_clear()


def test_summary_triggered_and_advances_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    # Low token thresholds so a handful of short turns crosses the trigger.
    monkeypatch.setenv("GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS", "40")
    monkeypatch.setenv("GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS", "16")
    get_settings.cache_clear()
    agent, client = _make_summary_agent(tmp_path)

    for i in range(6):
        agent.handle_message(f"消息{i}", source="qq_private", user_id="a", conversation_id="qq:user:a")

    summary = agent.store.get_conversation_summary("qq:user:a")
    assert summary is not None
    assert summary["summary"].startswith("滚动摘要")
    # boundary advanced past 0, keeping the most recent messages unsummarized
    assert summary["updated_until_message_id"] > 0
    assert len(client.complete_calls) >= 1
    get_settings.cache_clear()


def test_history_excludes_summarized_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS", "40")
    monkeypatch.setenv("GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS", "16")
    get_settings.cache_clear()
    agent, client = _make_summary_agent(tmp_path)

    for i in range(6):
        agent.handle_message(f"消息{i}", source="qq_private", user_id="a", conversation_id="qq:user:a")

    summary = agent.store.get_conversation_summary("qq:user:a")
    boundary = summary["updated_until_message_id"]
    # next turn should only load history after the boundary
    agent.handle_message("最新消息", source="qq_private", user_id="a", conversation_id="qq:user:a")
    last_chat = client.chat_calls[-1]
    history_contents = [m["content"] for m in last_chat["history"]]
    assert "消息0" not in history_contents
    assert all(
        row["id"] > boundary
        for row in agent.store.list_messages_after("qq:user:a", boundary)
    )
    get_settings.cache_clear()


def test_summarizer_skill_merges_previous_summary(tmp_path):
    client = SummaryCapableLLMClient()
    skill = SummarizerSkill(client)

    result = skill.summarize(
        [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好呀"}],
        previous_summary="用户叫小明。",
    )

    assert result is not None
    assert len(client.complete_calls) == 1
    sent = client.complete_calls[0]
    user_msg = sent[-1]["content"]
    assert "用户叫小明" in user_msg
    assert "你好" in user_msg


def test_trim_history_keeps_recent_within_budget(tmp_path):
    store = MemoryStore(tmp_path / "trim.db")
    agent = CoreAgent(store)
    history = [
        {"role": "user", "content": "很久以前的消息" * 50},
        {"role": "assistant", "content": "很久以前的回复" * 50},
        {"role": "user", "content": "最近的问题"},
        {"role": "assistant", "content": "最近的回复"},
    ]

    trimmed = agent._trim_history_to_budget(history, token_budget=60)

    # oldest large messages dropped, most recent kept
    assert history[-1] in trimmed
    assert history[-2] in trimmed
    assert history[0] not in trimmed


def test_trim_history_zero_budget_returns_all(tmp_path):
    store = MemoryStore(tmp_path / "trim2.db")
    agent = CoreAgent(store)
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]

    assert agent._trim_history_to_budget(history, token_budget=0) == history


# ── Router: prefix-only feedback matching ──────────────────────────────────
def test_router_feedback_requires_prefix():
    from gugabobo.core.router import Router
    r = Router()
    # These contain feedback keywords but mid-sentence → must go to chat
    assert r.route("这问题挺难的").skill == "chat"
    assert r.route("这电影我建议你看看").skill == "chat"
    assert r.route("你太长知识渊博了").skill == "chat"
    assert r.route("有个问题想请教").skill == "chat"


def test_router_feedback_matches_on_prefix():
    from gugabobo.core.router import Router
    r = Router()
    assert r.route("建议回复短一点").skill == "feedback"
    assert r.route("反馈：响应太慢").skill == "feedback"
    assert r.route("bug 有个错误").skill == "feedback"
    assert r.route("回复太长了，能短一点吗").skill == "feedback"


# ── Agent: background_summarize flag defaults off ──────────────────────────
def test_agent_background_summarize_off_by_default(tmp_path):
    store = MemoryStore(tmp_path / "bg.db")
    agent = CoreAgent(store)
    assert agent.background_summarize is False


def test_build_agent_enables_background_summarize(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "bg2.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    get_settings.cache_clear()
    from gugabobo.infra.runtime import build_agent as ba
    agent = ba()
    assert agent.background_summarize is True
    get_settings.cache_clear()
