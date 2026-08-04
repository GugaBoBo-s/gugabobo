from __future__ import annotations

import re
from datetime import datetime, timezone

from gugabobo.core.channel import ChannelContext
from pydantic import BaseModel

from gugabobo.infra.llm import AgentRuntime
from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger
from gugabobo.infra.napcat_client import NapCatClient
from gugabobo.infra.redaction import redact_sensitive
from gugabobo.memory.store import MemoryStore


_INTENT_SYSTEM_PROMPT = (
    "你是一个指令解析器。判断用户消息是否是在要求你主动通过 QQ 给某个联系人发送一条消息。"
    "只输出一个 JSON 对象，不要输出任何多余文字或 markdown。"
    'JSON 格式：{"action": "send" 或 "none", "target": "收件人名字或QQ号", "content": "要发送的正文"}。'
    "如果用户只是普通聊天、提问、闲聊，或没有明确指明发给谁，action 返回 none。"
    "target 是联系人的名字、备注或纯数字QQ号；content 是要替用户发送的原话正文。"
    "如果用户明确要求通过 Telegram 发送，action 必须返回 none，由 Telegram 工具处理。"
    "例子：用户说『用QQ给kc说 哈喽 你在干嘛』-> "
    '{"action":"send","target":"kc","content":"哈喽 你在干嘛"}。'
    "例子：用户说『今天天气怎么样』-> "
    '{"action":"none","target":"","content":""}。'
)
_CONFIRM_PATTERN = re.compile(r"^确认发送\s*#?(\d+)\s*$")
_CANCEL_PATTERN = re.compile(r"^取消发送\s*#?(\d+)\s*$")


class OutboundSkill:
    def __init__(
        self,
        runtime: AgentRuntime,
        store: MemoryStore,
        napcat_client: NapCatClient | None = None,
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.napcat_client = napcat_client or NapCatClient()

    def parse_intent(self, text: str) -> dict[str, str] | None:
        if not self.runtime.configured:
            return None
        try:
            result = self.runtime.run_messages(
                [
                    {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                output_type=OutboundIntent,
            )
        except Exception as exc:
            get_logger().warning("outbound intent parse failed: %s", self._safe_error(exc))
            return None
        parsed = result.output
        if not isinstance(parsed, OutboundIntent) or parsed.action != "send":
            return None
        target = parsed.target.strip()
        content = parsed.content.strip()
        if not target or not content:
            return None
        return {"target": target, "content": content}

    def handle(self, text: str, context: ChannelContext) -> str | None:
        confirm_match = _CONFIRM_PATTERN.fullmatch(text.strip())
        if confirm_match:
            return self.confirm(int(confirm_match.group(1)), context)
        cancel_match = _CANCEL_PATTERN.fullmatch(text.strip())
        if cancel_match:
            return self.cancel(int(cancel_match.group(1)), context)
        intent = self.parse_intent(text)
        if intent is None:
            return None
        return self.prepare(intent["target"], intent["content"], context)

    def prepare(self, target: str, content: str, context: ChannelContext) -> str:
        recipient = self._resolve_recipient(target)
        if isinstance(recipient, str):
            return recipient
        user_id, label = recipient
        draft_id = self.store.add_outbound_draft(
            conversation_id=context.conversation_id,
            actor_source=context.source,
            actor_user_id=context.user_id,
            target=target,
            recipient_user_id=user_id,
            recipient_label=label,
            content=content,
        )
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="outbound.draft",
            target=f"outbound_draft:{draft_id}",
            risk_level="high",
            detail=f"recipient:{user_id}",
        )
        return (
            f"已生成 QQ 发送草稿 #{draft_id}。\n"
            f"收件人：{label}（QQ {user_id}）\n"
            f"内容：{content}\n"
            f"回复“确认发送 #{draft_id}”执行，或回复“取消发送 #{draft_id}”。"
        )

    def confirm(self, draft_id: int, context: ChannelContext) -> str:
        draft = self._owned_pending_draft(draft_id, context)
        if isinstance(draft, str):
            return draft
        if self._expired(str(draft["expires_at"])):
            self.store.update_outbound_draft_status(draft_id, "expired")
            return f"发送草稿 #{draft_id} 已过期，请重新发起。"
        claimed = self.store.claim_outbound_draft(
            draft_id,
            actor_user_id=context.user_id,
            conversation_id=context.conversation_id,
        )
        if not claimed:
            current = self.store.get_outbound_draft(draft_id)
            status = current["status"] if current else "missing"
            return f"发送草稿 #{draft_id} 当前状态为 {status}。"
        try:
            self.napcat_client.send_private_msg(
                str(claimed["recipient_user_id"]),
                str(claimed["content"]),
            )
        except Exception as exc:
            error = self._safe_error(exc)
            self.store.update_outbound_draft_status(draft_id, "failed")
            self.store.add_audit_log(
                actor_source=context.source,
                actor_user_id=context.user_id,
                action="outbound.send",
                target=f"outbound_draft:{draft_id}",
                status="failed",
                risk_level="high",
                detail=error[:1000],
            )
            return f"草稿 #{draft_id} 发送失败：{error}"
        self.store.update_outbound_draft_status(draft_id, "sent")
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="outbound.send",
            target=f"outbound_draft:{draft_id}",
            status="ok",
            risk_level="high",
            detail=f"recipient:{draft['recipient_user_id']}",
        )
        return f"已发送草稿 #{draft_id} 给 {claimed['recipient_label']}。"

    def cancel(self, draft_id: int, context: ChannelContext) -> str:
        draft = self._owned_pending_draft(draft_id, context)
        if isinstance(draft, str):
            return draft
        self.store.update_outbound_draft_status(draft_id, "cancelled")
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="outbound.cancel",
            target=f"outbound_draft:{draft_id}",
            risk_level="high",
        )
        return f"已取消发送草稿 #{draft_id}。"

    def _resolve_recipient(self, target: str) -> tuple[str, str] | str:
        if target.isdigit():
            return target, target
        try:
            matches = self.napcat_client.find_friends(target)
        except Exception as exc:
            error = self._safe_error(exc)
            get_logger().warning("friend lookup failed target=%s error=%s", target, error)
            return f"查找好友时出错了：{error}。你可以直接告诉我对方的 QQ 号。"
        if not matches:
            return f"没有在好友里找到「{target}」。你可以直接告诉我对方的 QQ 号。"
        if len(matches) > 1:
            return f"找到多个可能的联系人：\n{_format_candidates(matches)}\n请用 QQ 号重新发起发送。"
        friend = matches[0]
        return str(friend.get("user_id")), _friend_label(friend)

    def _owned_pending_draft(
        self,
        draft_id: int,
        context: ChannelContext,
    ) -> dict[str, object] | str:
        draft = self.store.get_outbound_draft(draft_id)
        if not draft:
            return f"找不到发送草稿 #{draft_id}。"
        if (
            str(draft["actor_user_id"]) != context.user_id
            or str(draft["conversation_id"]) != context.conversation_id
        ):
            return "这个发送草稿不属于当前用户或会话。"
        if draft["status"] != "pending":
            return f"发送草稿 #{draft_id} 当前状态为 {draft['status']}。"
        return draft

    def _safe_error(self, error: object) -> str:
        settings = get_settings()
        return redact_sensitive(
            error,
            (
                settings.napcat_access_token,
                settings.moonshot_api_key,
                settings.deepseek_api_key,
                settings.openai_api_key,
            ),
        )

    def _expired(self, expires_at: str) -> bool:
        try:
            expires = datetime.fromisoformat(expires_at)
        except ValueError:
            return True
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return expires <= now


class OutboundIntent(BaseModel):
    action: str
    target: str = ""
    content: str = ""


def _friend_label(friend: dict[str, object]) -> str:
    remark = str(friend.get("remark", "")).strip()
    nickname = str(friend.get("nickname", "")).strip()
    return remark or nickname or str(friend.get("user_id", ""))


def _format_candidates(matches: list[dict[str, object]]) -> str:
    return "\n".join(
        f"- {_friend_label(friend)}（QQ {friend.get('user_id')}）" for friend in matches
    )
