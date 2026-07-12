from __future__ import annotations

import base64

import httpx

from gugabobo.infra.logs import get_logger

_MIME_BY_SIGNATURE = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
    (b"BM", "image/bmp"),
]


def _detect_mime(data: bytes) -> str:
    for signature, mime in _MIME_BY_SIGNATURE:
        if data.startswith(signature):
            return mime
    return "image/jpeg"


def url_to_data_uri(url: str, timeout: float = 20.0) -> str | None:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            content = response.content
    except Exception as exc:
        get_logger().warning("image download failed url=%s error=%s", url, exc)
        return None
    if not content:
        return None
    mime = _detect_mime(content)
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def urls_to_data_uris(urls: list[str], timeout: float = 20.0) -> list[str]:
    data_uris = []
    for url in urls:
        data_uri = url_to_data_uri(url, timeout=timeout)
        if data_uri:
            data_uris.append(data_uri)
    return data_uris
