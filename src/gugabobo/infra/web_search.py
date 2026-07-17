from __future__ import annotations

from dataclasses import dataclass

import httpx

from gugabobo.config import Settings, get_settings
from gugabobo.infra.logs import get_logger


@dataclass(frozen=True)
class SearchResult:
    title: str
    link: str
    snippet: str


class WebSearchClient:
    """Thin wrapper over the Serper (google.serper.dev) search API.

    Serper proxies Google results in an LLM-friendly JSON shape. The server may
    sit behind the GFW, so requests optionally go through web_search_proxy
    (e.g. the local xray SOCKS endpoint), mirroring TelegramClient.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.serper_api_key)

    @property
    def _proxy(self) -> str | None:
        return self.settings.web_search_proxy or None

    def search(self, query: str, num: int | None = None) -> list[SearchResult]:
        if not self.configured:
            raise RuntimeError("SERPER_API_KEY is not configured")
        count = num or self.settings.web_search_max_results
        url = f"{self.settings.serper_base_url.rstrip('/')}/search"
        headers = {
            "X-API-KEY": self.settings.serper_api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": count}
        with httpx.Client(
            timeout=self.settings.web_search_timeout_seconds,
            proxy=self._proxy,
            follow_redirects=True,
        ) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return _parse_results(data, count)


def _parse_results(data: dict[str, object], count: int) -> list[SearchResult]:
    results: list[SearchResult] = []

    # An "answerBox" / "knowledgeGraph" is Serper's direct answer; surface it first.
    answer = data.get("answerBox")
    if isinstance(answer, dict):
        snippet = str(answer.get("answer") or answer.get("snippet") or "").strip()
        if snippet:
            results.append(
                SearchResult(
                    title=str(answer.get("title", "直接答案")).strip() or "直接答案",
                    link=str(answer.get("link", "")).strip(),
                    snippet=snippet,
                )
            )

    organic = data.get("organic")
    if isinstance(organic, list):
        for item in organic:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            link = str(item.get("link", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if title or snippet:
                results.append(SearchResult(title=title, link=link, snippet=snippet))
            if len(results) >= count:
                break

    return results[:count]


def format_results(results: list[SearchResult]) -> str:
    if not results:
        return "没有找到相关的网页结果。"
    lines = []
    for index, result in enumerate(results, start=1):
        block = f"{index}. {result.title}\n{result.snippet}"
        if result.link:
            block += f"\n{result.link}"
        lines.append(block)
    return "\n\n".join(lines)


def run_web_search(query: str, settings: Settings | None = None) -> str:
    client = WebSearchClient(settings)
    if not client.configured:
        return "错误：Web 搜索未配置（缺少 SERPER_API_KEY）。"
    try:
        results = client.search(query)
    except Exception as exc:
        get_logger().warning("web search failed: %s", exc)
        return f"Web 搜索失败：{exc}"
    return format_results(results)
