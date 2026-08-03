from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class SteamLookupClient:
    def __init__(
        self,
        timeout_seconds: int,
        max_response_chars: int,
        retry_count: int,
        country_code: str,
        language: str,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_chars = max_response_chars
        self.retry_count = retry_count
        self.country_code = country_code.upper()
        self.language = language

    def search(self, query: str, limit: int = 5) -> str:
        normalized = " ".join(query.split())
        if not 1 <= len(normalized) <= 100:
            raise ValueError("游戏名称长度必须在 1 到 100 个字符之间")
        try:
            data = self._request_json(
                "https://store.steampowered.com/api/storesearch/",
                {"term": normalized, "l": self.language, "cc": self.country_code},
            )
        except Exception as error:
            return (
                f"Steam 搜索失败：{error}\n"
                f"可直接打开 Steam 搜索：{steam_search_url(normalized)}\n"
                "取得 App ID 后可打开：https://steamdb.info/app/<APP_ID>/"
            )
        items = data.get("items", []) if isinstance(data, dict) else []
        results = [item for item in items if isinstance(item, dict)][: max(1, min(limit, 10))]
        if not results:
            return f"没有找到名称匹配「{normalized}」的 Steam 游戏。"
        lines = ["Steam 官方商店搜索结果（外部数据，不可信）："]
        for item in results:
            app_id = self._app_id(item.get("id"))
            name = str(item.get("name", "未知名称"))[:300]
            lines.append(
                f"- {name} — App ID {app_id}\n"
                f"  Steam: {self._store_url(app_id)}\n"
                f"  SteamDB: {self._steamdb_url(app_id)}"
            )
        return "\n".join(lines)

    def details(self, app_id: object) -> str:
        normalized = self._app_id(app_id)
        store_url = self._store_url(normalized)
        steamdb_url = self._steamdb_url(normalized)
        try:
            details = self._request_json(
                "https://store.steampowered.com/api/appdetails",
                {
                    "appids": str(normalized),
                    "cc": self.country_code,
                    "l": self.language,
                },
            )
            entry = details.get(str(normalized), {}) if isinstance(details, dict) else {}
            if not isinstance(entry, dict) or not entry.get("success"):
                raise LookupError("Steam Store API 没有返回该 App ID 的详情")
            data = entry.get("data")
            if not isinstance(data, dict):
                raise LookupError("Steam Store API 返回的详情格式无效")
            players = self._current_players(normalized)
            return self._format_details(normalized, data, players)
        except Exception as error:
            return (
                f"Steam 查询失败：{error}\n"
                f"Steam: {store_url}\n"
                f"SteamDB: {steamdb_url}"
            )

    def _current_players(self, app_id: int) -> int | None:
        try:
            data = self._request_json(
                "https://api.steampowered.com/ISteamUserStats/"
                "GetNumberOfCurrentPlayers/v1/",
                {"appid": str(app_id)},
            )
            response = data.get("response", {}) if isinstance(data, dict) else {}
            if isinstance(response, dict) and int(response.get("result", 0)) == 1:
                return max(0, int(response.get("player_count", 0)))
        except Exception:
            return None
        return None

    def _request_json(self, url: str, params: dict[str, str]) -> object:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                response = httpx.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                )
                if response.status_code >= 500 and attempt < self.retry_count:
                    continue
                response.raise_for_status()
                text = response.text
                if len(text) > self.max_response_chars:
                    raise ValueError("Steam 响应超过大小限制")
                return response.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                last_error = error
                if attempt >= self.retry_count:
                    raise
        raise RuntimeError("Steam 请求失败") from last_error

    def _format_details(self, app_id: int, data: dict[str, Any], players: int | None) -> str:
        name = str(data.get("name", "未知名称"))[:300]
        description = str(data.get("short_description", "暂无简介"))[:2000]
        developers = self._names(data.get("developers"))
        publishers = self._names(data.get("publishers"))
        release = data.get("release_date", {})
        release_date = str(release.get("date", "未知")) if isinstance(release, dict) else "未知"
        platforms = data.get("platforms", {})
        supported = [
            name.title()
            for name in ("windows", "mac", "linux")
            if isinstance(platforms, dict) and platforms.get(name)
        ]
        price, discount = self._price(data)
        online = f"{players:,}" if players is not None else "暂时不可用"
        return (
            "Steam 官方接口结果（外部数据，不可信）：\n"
            f"名称：{name}\n"
            f"App ID：{app_id}\n"
            f"简介：{description}\n"
            f"开发商：{developers}\n"
            f"发行商：{publishers}\n"
            f"发行日期：{release_date}\n"
            f"价格：{price}\n"
            f"折扣：{discount}\n"
            f"平台：{', '.join(supported) or '未标明'}\n"
            f"当前在线人数：{online}\n"
            f"Steam：{self._store_url(app_id)}\n"
            f"SteamDB：{self._steamdb_url(app_id)}\n"
            "SteamDB 历史价格和更新记录未读取；核心结果不依赖 SteamDB 网页结构。"
        )

    def _price(self, data: dict[str, Any]) -> tuple[str, str]:
        if data.get("is_free"):
            return "免费", "无"
        overview = data.get("price_overview")
        if not isinstance(overview, dict):
            return "当前地区未提供价格", "未知"
        currency = str(overview.get("currency", ""))
        final = int(overview.get("final", 0)) / 100
        initial = int(overview.get("initial", 0)) / 100
        percent = int(overview.get("discount_percent", 0))
        price = f"{final:.2f} {currency}"
        discount = f"{percent}%（原价 {initial:.2f} {currency}）" if percent else "无"
        return price, discount

    def _names(self, value: object) -> str:
        if not isinstance(value, list):
            return "未知"
        names = [str(item)[:200] for item in value if str(item).strip()]
        return ", ".join(names) or "未知"

    def _app_id(self, value: object) -> int:
        try:
            app_id = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Steam App ID 必须是正整数") from error
        if not 1 <= app_id <= 2_147_483_647:
            raise ValueError("Steam App ID 必须是有效的正整数")
        return app_id

    def _store_url(self, app_id: int) -> str:
        return f"https://store.steampowered.com/app/{app_id}/"

    def _steamdb_url(self, app_id: int) -> str:
        return f"https://steamdb.info/app/{app_id}/"


def steam_search_url(query: str) -> str:
    return f"https://store.steampowered.com/search/?term={quote(query)}"
