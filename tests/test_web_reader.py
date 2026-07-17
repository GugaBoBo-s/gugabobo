from __future__ import annotations

from gugabobo.infra.web_reader import html_to_text, run_read_url


def test_html_to_text_extracts_title_and_body():
    html = """
    <html><head><title>示例页面</title>
    <style>.x{color:red}</style><script>var a=1;</script></head>
    <body><h1>大标题</h1><p>第一段正文。</p><p>第二段正文。</p></body></html>
    """
    title, text = html_to_text(html)

    assert title == "示例页面"
    assert "大标题" in text
    assert "第一段正文。" in text
    assert "第二段正文。" in text
    # script/style content must be dropped
    assert "var a=1" not in text
    assert "color:red" not in text


def test_html_to_text_handles_plain_fallback():
    # even malformed markup returns something rather than crashing
    title, text = html_to_text("<p>hi<p>there")
    assert "hi" in text and "there" in text


def test_run_read_url_rejects_non_http():
    assert "http" in run_read_url("ftp://example.com")
    assert "http" in run_read_url("not a url")


def test_run_read_url_injected_via_client(monkeypatch, tmp_path):
    from gugabobo.config import get_settings
    from gugabobo.infra import web_reader as wr

    get_settings.cache_clear()

    class FakeReader:
        def __init__(self, *a, **k):
            pass

        def fetch(self, url):
            return "页面标题", "这是页面正文。" * 10

    monkeypatch.setattr(wr, "WebReaderClient", FakeReader)
    out = wr.run_read_url("https://example.com")
    assert "页面标题" in out
    assert "页面正文" in out
    get_settings.cache_clear()


def test_run_read_url_truncates_long_content(monkeypatch):
    from gugabobo.config import get_settings
    from gugabobo.infra import web_reader as wr

    monkeypatch.setenv("GUGABOBO_READ_URL_MAX_CHARS", "500")
    get_settings.cache_clear()

    class FakeReader:
        def __init__(self, *a, **k):
            pass

        def fetch(self, url):
            return "", "x" * 5000

    monkeypatch.setattr(wr, "WebReaderClient", FakeReader)
    out = wr.run_read_url("https://example.com")
    assert "已截断" in out
    get_settings.cache_clear()


def test_run_read_url_handles_fetch_error(monkeypatch):
    from gugabobo.config import get_settings
    from gugabobo.infra import web_reader as wr

    get_settings.cache_clear()

    class BoomReader:
        def __init__(self, *a, **k):
            pass

        def fetch(self, url):
            raise RuntimeError("timeout")

    monkeypatch.setattr(wr, "WebReaderClient", BoomReader)
    out = wr.run_read_url("https://example.com")
    assert "失败" in out
    get_settings.cache_clear()
