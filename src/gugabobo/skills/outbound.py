from __future__ import annotations

import json

from gugabobo.infra.llm import OpenAICompatibleClient
from gugabobo.infra.logs import get_logger
from gugabobo.infra.napcat_client import NapCatClient

_INTENT_SYSTEM_PROMPT = (
    "你是一个指令解析器。判断用户消息是否是在要求你主动通过 QQ 给某个联系人发送一条消息。"
    "只输出一个 JSON 对象，不要输出任何多余文字或 markdown。"
    'JSON 格式：{"action": "send" 或 "none", "target": "收件人名字或QQ号", "content": "要发送的正文"}。'
    "如果用户只是普通聊天、提问、闲聊，或没有明确指明发给谁，action 返回 none。"
    "target 是联系人的名字、备注或纯数字QQ号；content 是要替用户发送的原话正文。"
    "例子：用户说『用QQ给kc说 哈喽 你在干嘛』-> "
    '{"action":"send","target":"kc","content":"哈喽 你在干嘛"}。'
    "例子：用户说『今天天气怎么样』-> "
    '{"action":"none","target":"","content":""}。'
)


class OutboundSkill:
    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        napcat_client: NapCatClient | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.napcat_client = napcat_client or NapCatClient()

    def parse_intent(self, text: str) -> dict[str, str] | None:
        if not self.llm_client.configured:
            return None
        try:
            raw = self.llm_client.complete(
                [
                    {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ]
            )
            parsed = json.loads(_strip_code_fence(raw))
        except Exception as exc:
            get_logger().warning("outbound intent parse failed: %s", exc)
            return None
        if not isinstance(parsed, dict):
            return None
        if parsed.get("action") != "send":
            return None
        target = str(parsed.get("target", "")).strip()
        content = str(parsed.get("content", "")).strip()
        if not target or not content:
            return None
        return {"target": target, "content": content}

    def handle(self, text: str) -> str | None:
        intent = self.parse_intent(text)
        if intent is None:
            return None
        return self.send(intent["target"], intent["content"])

    def send(self, target: str, content: str) -> str:
        if target.isdigit():
            try:
                self.napcat_client.send_private_msg(target, content)
            except Exception as exc:
                get_logger().warning("outbound send failed target=%s error=%s", target, exc)
                return f"发送给 {target} 失败了：{exc}"
            return f"已发送给 QQ {target}：{content}"

        try:
            matches = self.napcat_client.find_friends(target)
        except Exception as exc:
            get_logger().warning("friend lookup failed target=%s error=%s", target, exc)
            return f"查找好友时出错了：{exc}。你可以直接告诉我对方的 QQ 号。"

        if not matches:
            return f"没有在好友里找到「{target}」。你可以直接告诉我对方的 QQ 号，我来发。"
        if len(matches) > 1:
            return f"找到多个可能的联系人：\n{_format_candidates(matches)}\n你要发给哪个 QQ 号？"

        friend = matches[0]
        user_id = str(friend.get("user_id"))
        label = _friend_label(friend)
        try:
            self.napcat_client.send_private_msg(user_id, content)
        except Exception as exc:
            get_logger().warning("outbound send failed target=%s error=%s", user_id, exc)
            return f"发送给 {label} 失败了：{exc}"
        return f"已发送给 {label}（QQ {user_id}）：{content}"


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _friend_label(friend: dict[str, object]) -> str:
    remark = str(friend.get("remark", "")).strip()
    nickname = str(friend.get("nickname", "")).strip()
    return remark or nickname or str(friend.get("user_id", ""))


def _format_candidates(matches: list[dict[str, object]]) -> str:
    lines = []
    for friend in matches:
        lines.append(f"- {_friend_label(friend)}（QQ {friend.get('user_id')}）")
    return "\n".join(lines)
