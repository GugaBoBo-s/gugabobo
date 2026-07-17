from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

from gugabobo.config import Settings, get_settings
from gugabobo.infra.logs import get_logger

# Tags whose text content is noise for a reader (scripts, styles, nav chrome).
_SKIP_TAGS = {"script", "style", "noscript", "head", "svg", "nav", "footer", "header", "form"}
# Block-level tags that should produce a line break in the extracted text.
_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "ul", "ol", "table", "blockquote", "pre",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        # Title capture takes priority: <title> lives inside <head>, which is a
        # skipped tag, so this must run before the skip-depth check.
        if self._in_title:
            self._title += data
            return
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self._title.split())

    @property
    def text(self) -> str:
        raw = " ".join(self._parts)
        # collapse runs of spaces, keep intentional newlines
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        # Malformed markup: fall back to a crude tag strip.
        stripped = re.sub(r"<[^>]+>", " ", html)
        return "", re.sub(r"\s+", " ", stripped).strip()
    return parser.title, parser.text


class WebReaderClient:
    """Fetches a URL and returns readable plain text.

    Shares web_search_proxy so a GFW'd server can reach foreign pages through
    the local xray SOCKS endpoint.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def _proxy(self) -> str | None:
        return self.settings.web_search_proxy or None

    def fetch(self, url: str) -> tuple[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; gugabobo/1.0; +https://github.com/GugaBoBo-s/gugabobo)"
            )
        }
        with httpx.Client(
            timeout=self.settings.read_url_timeout_seconds,
            proxy=self._proxy,
            follow_redirects=True,
        ) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            body = response.text
        if "html" in content_type.lower() or body.lstrip().startswith("<"):
            return html_to_text(body)
        # Plain text / JSON / other: return as-is (no title).
        return "", body.strip()


def run_read_url(url: str, settings: Settings | None = None) -> str:
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return "错误：请提供以 http:// 或 https:// 开头的完整网址。"
    resolved = settings or get_settings()
    try:
        title, text = WebReaderClient(resolved).fetch(url)
    except Exception as exc:
        get_logger().warning("read url failed: %s", exc)
        return f"读取网页失败：{exc}"
    if not text:
        return "这个网页没有可读的正文内容。"
    limit = resolved.read_url_max_chars
    truncated = text[:limit]
    suffix = "\n\n（正文过长，已截断）" if len(text) > limit else ""
    header = f"标题：{title}\n\n" if title else ""
    return f"{header}{truncated}{suffix}"
