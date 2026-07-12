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

    def get_friend_list(self) -> list[dict[str, object]]:
        response = self.call_with_result("get_friend_list", {})
        data = response.get("data")
        if isinstance(data, list):
            return data
        return []

    def find_friends(self, target: str) -> list[dict[str, object]]:
        query = target.strip()
        lowered = query.lower()
        matches = []
        for friend in self.get_friend_list():
            remark = str(friend.get("remark", ""))
            nickname = str(friend.get("nickname", ""))
            if lowered and (lowered in remark.lower() or lowered in nickname.lower()):
                matches.append(friend)
        return matches

    def call(self, action: str, payload: dict[str, object]) -> None:
        self.call_with_result(action, payload)

    def call_with_result(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        headers = {}
        if self.settings.napcat_access_token:
            headers["Authorization"] = f"Bearer {self.settings.napcat_access_token}"
        url = f"{self.settings.napcat_api_url.rstrip('/')}/{action}"
        with httpx.Client(timeout=15) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
