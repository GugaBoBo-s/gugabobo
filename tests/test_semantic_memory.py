from types import SimpleNamespace

from gugabobo.config import Settings
from gugabobo.infra.semantic_memory import VexorMemorySearch


def test_vexor_semantic_memory_returns_ranked_memory(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def set_config_json(self, config):
            captured["config"] = config

        def search(self, query, **kwargs):
            captured["query"] = query
            captured["search"] = kwargs
            return SimpleNamespace(results=[SimpleNamespace(path="memory-2.txt")])

    monkeypatch.setattr("vexor.VexorClient", FakeClient)
    search = VexorMemorySearch(
        Settings(
            _env_file=None,
            vexor_memory_enabled=True,
            vexor_api_key="embedding-secret",
        )
    )
    memories = [
        {"id": 1, "content": "用户喜欢蓝色"},
        {"id": 2, "content": "用户正在重构 AI"},
    ]

    result = search.search("最近在开发什么", memories, 1)

    assert result == [memories[1]]
    assert captured["query"] == "最近在开发什么"
    assert captured["search"]["no_cache"] is True
    assert captured["config"]["api_key"] == "embedding-secret"


def test_vexor_memory_falls_back_when_not_configured():
    memories = [{"id": 1, "content": "first"}, {"id": 2, "content": "second"}]
    search = VexorMemorySearch(Settings(_env_file=None, vexor_memory_enabled=False))

    assert search.search("query", memories, 1) == [memories[0]]
