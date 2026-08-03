import json
from types import SimpleNamespace

import httpx
import pytest

from gugabobo.infra.steam_client import SteamLookupClient


def _response(payload, status_code=200):
    text = json.dumps(payload)

    def raise_for_status():
        if status_code >= 400:
            request = httpx.Request("GET", "https://steam.example")
            response = httpx.Response(status_code, request=request)
            raise httpx.HTTPStatusError("failed", request=request, response=response)

    return SimpleNamespace(
        status_code=status_code,
        text=text,
        json=lambda: payload,
        raise_for_status=raise_for_status,
    )


def _client(**overrides):
    values = {
        "timeout_seconds": 10,
        "max_response_chars": 100000,
        "retry_count": 1,
        "country_code": "CN",
        "language": "schinese",
    }
    values.update(overrides)
    return SteamLookupClient(**values)


def test_steam_search_returns_app_ids_and_links(monkeypatch):
    captured = {}

    def get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _response({"items": [{"id": 570, "name": "Dota 2"}]})

    monkeypatch.setattr("gugabobo.infra.steam_client.httpx.get", get)

    result = _client().search("Dota 2")

    assert "App ID 570" in result
    assert "https://store.steampowered.com/app/570/" in result
    assert "https://steamdb.info/app/570/" in result
    assert captured["params"]["term"] == "Dota 2"


def test_steam_details_combines_store_data_and_current_players(monkeypatch):
    responses = iter(
        [
            _response(
                {
                    "570": {
                        "success": True,
                        "data": {
                            "name": "Dota 2",
                            "short_description": "A competitive game.",
                            "developers": ["Valve"],
                            "publishers": ["Valve"],
                            "release_date": {"date": "9 Jul, 2013"},
                            "price_overview": {
                                "currency": "CNY",
                                "initial": 1000,
                                "final": 500,
                                "discount_percent": 50,
                            },
                            "platforms": {"windows": True, "mac": True, "linux": True},
                        },
                    }
                }
            ),
            _response({"response": {"result": 1, "player_count": 123456}}),
        ]
    )
    monkeypatch.setattr(
        "gugabobo.infra.steam_client.httpx.get",
        lambda *args, **kwargs: next(responses),
    )

    result = _client().details(570)

    assert "名称：Dota 2" in result
    assert "开发商：Valve" in result
    assert "价格：5.00 CNY" in result
    assert "折扣：50%" in result
    assert "当前在线人数：123,456" in result
    assert "Windows, Mac, Linux" in result
    assert "历史价格和更新记录未读取" in result


def test_steam_request_retries_server_error(monkeypatch):
    responses = iter(
        [
            _response({}, status_code=503),
            _response({"items": [{"id": 730, "name": "Counter-Strike 2"}]}),
        ]
    )
    calls = []

    def get(*args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr("gugabobo.infra.steam_client.httpx.get", get)

    result = _client(retry_count=1).search("Counter-Strike 2")

    assert "App ID 730" in result
    assert len(calls) == 2


def test_steam_details_failure_returns_direct_links(monkeypatch):
    monkeypatch.setattr(
        "gugabobo.infra.steam_client.httpx.get",
        lambda *args, **kwargs: _response({}, status_code=503),
    )

    result = _client(retry_count=0).details(570)

    assert "Steam 查询失败" in result
    assert "https://store.steampowered.com/app/570/" in result
    assert "https://steamdb.info/app/570/" in result


def test_steam_validates_query_app_id_and_response_size(monkeypatch):
    with pytest.raises(ValueError, match="游戏名称长度"):
        _client().search("")
    with pytest.raises(ValueError, match="App ID"):
        _client().details("not-an-id")

    monkeypatch.setattr(
        "gugabobo.infra.steam_client.httpx.get",
        lambda *args, **kwargs: _response({"items": [{"id": 570, "name": "x" * 2000}]}),
    )
    result = _client(max_response_chars=1000).search("Dota")

    assert "响应超过大小限制" in result
    assert "store.steampowered.com/search" in result
