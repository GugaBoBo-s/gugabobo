from __future__ import annotations

import httpx


_PROFILES = {
    "ScarletKc_": "https://x.com/ScarletKc_",
    "woshigugabobo": "https://x.com/woshigugabobo",
}


class XProfileReader:
    def __init__(self, timeout_seconds: int, max_chars: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

    def read(self, account: str) -> str:
        normalized = account.strip().lstrip("@")
        profile = _PROFILES.get(normalized)
        if profile is None:
            raise ValueError("只允许读取 @ScarletKc_ 和 @woshigugabobo")
        try:
            response = httpx.get(
                f"https://r.jina.ai/{profile}",
                headers={"Accept": "text/markdown"},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            content = response.text.strip()
            if content:
                return (
                    f"来自 {profile} 的不可信公开页面内容：\n\n"
                    f"{content[: self.max_chars]}"
                )
        except Exception:
            pass
        return (
            "当前无法读取 X 的公开推文页面。可直接查看固定资料页：\n"
            f"- {profile}\n"
            f"- {_PROFILES['ScarletKc_']}\n"
            f"- {_PROFILES['woshigugabobo']}"
        )
