from __future__ import annotations

from gugabobo.infra.web_search import _parse_results, format_results, run_web_search


def test_parse_results_puts_answer_box_first():
    data = {
        "answerBox": {"title": "Python 版本", "answer": "3.13", "link": "http://py"},
        "organic": [
            {"title": "结果A", "link": "http://a", "snippet": "摘要A"},
        ],
    }

    results = _parse_results(data, count=6)

    assert results[0].snippet == "3.13"
    assert results[0].title == "Python 版本"
    assert results[1].title == "结果A"


def test_parse_results_organic_only_and_limit():
    data = {
        "organic": [
            {"title": f"t{i}", "link": f"http://{i}", "snippet": f"s{i}"}
            for i in range(10)
        ]
    }

    results = _parse_results(data, count=3)

    assert len(results) == 3
    assert results[0].title == "t0"


def test_parse_results_empty():
    assert _parse_results({}, count=6) == []


def test_format_results_empty():
    assert format_results([]) == "没有找到相关的网页结果。"


def test_run_web_search_unconfigured(monkeypatch):
    monkeypatch.setenv("GUGABOBO_SERPER_API_KEY", "")
    from gugabobo.config import get_settings

    get_settings.cache_clear()
    out = run_web_search("test")
    assert "未配置" in out
    get_settings.cache_clear()


def test_run_web_search_handles_error(monkeypatch, tmp_path):
    monkeypatch.setenv("GUGABOBO_SERPER_API_KEY", "test-key")
    from gugabobo.config import get_settings
    from gugabobo.infra import web_search as ws

    get_settings.cache_clear()

    class BoomClient:
        configured = True

        def __init__(self, *a, **k):
            pass

        def search(self, query, num=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(ws, "WebSearchClient", BoomClient)
    out = ws.run_web_search("test")
    assert "失败" in out
    get_settings.cache_clear()
