from __future__ import annotations

import re
from collections.abc import Iterable


_PATTERNS = (
    re.compile(r"(https://api\.telegram\.org/(?:file/)?bot)[^/\s]+", re.IGNORECASE),
    re.compile(r"([a-z][a-z0-9+.-]*://)[^/@\s]+:[^/@\s]+@", re.IGNORECASE),
    re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{20,}\b", re.IGNORECASE),
)


def redact_sensitive(value: object, secrets: Iterable[str] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    text = _PATTERNS[0].sub(r"\1<redacted>", text)
    text = _PATTERNS[1].sub(r"\1<redacted>@", text)
    for pattern in _PATTERNS[2:]:
        text = pattern.sub("<redacted>", text)
    return text
