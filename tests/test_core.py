from gugabobo.core.agent import CoreAgent
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

    reply = agent.handle_message("建议回复短一点", source="test", user_id="u1")

    assert "已记录反馈" in reply
    assert agent.store.count_feedbacks() == 1
    get_settings.cache_clear()


class FakeLLMClient:
    configured = True

    def chat(self, text, persona):
        return type("Result", (), {"content": f"kimi reply: {text}", "model": "kimi-k2.6"})()


class DisabledLLMClient:
    configured = False


def test_chat_skill_uses_llm_when_configured():
    skill = ChatSkill(Persona(), llm_client=FakeLLMClient())

    reply = skill.reply("你好")

    assert reply == "kimi reply: 你好"


def test_chat_skill_falls_back_without_llm():
    skill = ChatSkill(Persona(), llm_client=DisabledLLMClient())

    reply = skill.reply("你好")

    assert "已收到" in reply


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
