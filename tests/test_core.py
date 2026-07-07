from gugabobo.core.agent import CoreAgent
from gugabobo.core.channel import ChannelContext
from gugabobo.core.persona import Persona
from gugabobo.config import get_settings
from gugabobo.infra.llm import DeepSeekClient, MoonshotClient, build_llm_client
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill


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

    def chat(self, text, persona, history=None, system_context=None):
        return type("Result", (), {"content": f"kimi reply: {text}", "model": "kimi-k2.6"})()


class HistoryCapturingLLMClient:
    configured = True

    def __init__(self):
        self.histories = []
        self.system_contexts = []

    def chat(self, text, persona, history=None, system_context=None):
        self.histories.append(history or [])
        self.system_contexts.append(system_context or [])
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
