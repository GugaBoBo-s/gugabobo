from __future__ import annotations

import httpx

from gugabobo.config import get_settings


class NapCatClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_private_msg(self, user_id: str, message: str) -> None:
        self.call("send_private_msg", {"user_id": int(user_id), "message": message})

    def send_group_msg(self, group_id: str, message: str) -> None:
        self.call("send_group_msg", {"group_id": int(group_id), "message": message})

    def call(self, action: str, payload: dict[str, object]) -> None:
        headers = {}
        if self.settings.napcat_access_token:
            headers["Authorization"] = f"Bearer {self.settings.napcat_access_token}"
        url = f"{self.settings.napcat_api_url.rstrip('/')}/{action}"
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
