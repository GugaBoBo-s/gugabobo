import pytest

from gugabobo.config import get_settings
from gugabobo.core.persona import Persona
from gugabobo.infra.llm import AgentResult
from gugabobo.infra.prompt_guidance import PromptGuidanceStore
from gugabobo.skills.chat import ChatSkill


def test_prompt_guidance_reads_and_replaces_fixed_documents(tmp_path):
    (tmp_path / "soul.md").write_text("original soul", encoding="utf-8")
    store = PromptGuidanceStore(tmp_path, 5000)

    assert store.read("soul.md") == "original soul"
    assert "Project guidance from soul.md" in store.instructions()[0]
    assert "下一条 AI 消息" in store.replace("rules.md", "new rules")
    assert (tmp_path / "rules.md").read_text(encoding="utf-8") == "new rules"


def test_prompt_guidance_rejects_arbitrary_files(tmp_path):
    store = PromptGuidanceStore(tmp_path, 5000)

    with pytest.raises(ValueError, match="只能访问"):
        store.replace("AGENTS.md", "override")


def test_chat_agent_loads_guidance_as_instructions(tmp_path, monkeypatch):
    (tmp_path / "soul.md").write_text("be curious", encoding="utf-8")
    (tmp_path / "rules.md").write_text("keep permissions", encoding="utf-8")
    monkeypatch.setenv("GUGABOBO_PROMPT_GUIDANCE_DIR", str(tmp_path))
    get_settings.cache_clear()

    class Runtime:
        configured = True

        def run(self, text, **kwargs):
            self.instructions = kwargs["instructions"]
            return AgentResult("ok", "test")

    runtime = Runtime()
    skill = ChatSkill(Persona(), llm_client=runtime)

    assert skill.reply("hello") == "ok"
    assert any("be curious" in item for item in runtime.instructions)
    assert any("keep permissions" in item for item in runtime.instructions)
    get_settings.cache_clear()
