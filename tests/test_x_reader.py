from types import SimpleNamespace

import pytest

from gugabobo.infra.x_reader import XProfileReader


def test_x_reader_fetches_allowlisted_public_profile(monkeypatch):
    captured = {}

    def get(url, **kwargs):
        captured["url"] = url
        return SimpleNamespace(
            raise_for_status=lambda: None,
            text="recent public post",
        )

    monkeypatch.setattr("gugabobo.infra.x_reader.httpx.get", get)

    result = XProfileReader(10, 5000).read("@ScarletKc_")

    assert captured["url"] == "https://r.jina.ai/https://x.com/ScarletKc_"
    assert "不可信公开页面内容" in result
    assert "recent public post" in result


def test_x_reader_returns_profile_links_when_public_page_is_blocked(monkeypatch):
    monkeypatch.setattr(
        "gugabobo.infra.x_reader.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")),
    )

    result = XProfileReader(10, 5000).read("woshigugabobo")

    assert "当前无法读取" in result
    assert "https://x.com/ScarletKc_" in result
    assert "https://x.com/woshigugabobo" in result


def test_x_reader_rejects_unlisted_account():
    with pytest.raises(ValueError, match="只允许读取"):
        XProfileReader(10, 5000).read("someone_else")
