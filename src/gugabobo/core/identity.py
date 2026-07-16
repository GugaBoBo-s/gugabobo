from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace

from gugabobo.core.access import context_access_role
from gugabobo.core.channel import ChannelContext
from gugabobo.memory.store import MemoryStore


_LINK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LINK_PREFIXES = (
    "绑定账号",
    "绑定其他账号",
    "关联账号",
    "/link",
    "link account",
    "link",
)


@dataclass(frozen=True)
class IdentityCommandResult:
    context: ChannelContext
    response: str | None = None


class IdentityService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def resolve_context(self, context: ChannelContext) -> ChannelContext:
        if context.platform not in {"qq", "telegram"} or not context.user_id:
            return context
        account = self.store.ensure_channel_account(
            platform=context.platform,
            platform_user_id=context.user_id,
            role=context_access_role(context),
        )
        person_id = int(account["person_id"])
        metadata = dict(context.metadata or {})
        metadata["person_id"] = person_id
        metadata["channel_conversation_id"] = context.conversation_id
        conversation_id = context.conversation_id
        if context.channel_type == "private":
            conversation_id = self.direct_conversation_id(person_id)
            self.store.migrate_private_conversation(
                context.conversation_id,
                conversation_id,
            )
        return replace(
            context,
            person_id=person_id,
            conversation_id=conversation_id,
            metadata=metadata,
        )

    def handle_command(self, text: str, context: ChannelContext) -> IdentityCommandResult:
        argument = self._parse_link_command(text)
        if argument is None:
            return IdentityCommandResult(context=context)
        if context.platform not in {"qq", "telegram"} or context.channel_type != "private":
            return IdentityCommandResult(
                context=context,
                response="请在 QQ 或 Telegram 私聊中绑定账号。群聊不会参与账号绑定。",
            )
        if context.person_id is None:
            context = self.resolve_context(context)
        if argument == "":
            return IdentityCommandResult(
                context=context,
                response=self._create_link_code(context),
            )
        code = self._normalize_code(argument)
        if not code:
            return IdentityCommandResult(
                context=context,
                response="绑定码格式不正确。请发送：绑定账号 GB-XXXX-XXXX-XXXX",
            )
        result = self.store.consume_account_link_code(
            code_hash=self._hash_code(code),
            target_platform=context.platform,
            target_user_id=context.user_id,
        )
        status = str(result["status"])
        if status in {"linked", "already_linked"}:
            resolved = self.resolve_context(context)
            self.store.add_audit_log(
                actor_source=context.source,
                actor_user_id=context.user_id,
                action="identity.account_linked",
                target=f"person:{resolved.person_id}",
                status="ok",
                risk_level="sensitive",
                detail=f"platform={context.platform}",
            )
            if status == "already_linked":
                response = "这两个账号已经属于同一个用户，上下文已经共享。"
            else:
                response = "账号绑定成功。QQ 和 Telegram 私聊现在共享同一身份、上下文和记忆。"
            return IdentityCommandResult(context=resolved, response=response)
        responses = {
            "invalid": "绑定码无效或已经使用，请从另一个账号重新生成。",
            "expired": "绑定码已经过期，请从另一个账号重新生成。",
            "same_account": "不能在生成绑定码的同一个账号上完成绑定。",
            "same_platform": "目前只支持在 QQ 与 Telegram 之间绑定账号。",
            "target_missing": "当前账号尚未建立身份记录，请重新发送绑定命令。",
            "stale_identity": "身份记录已经变化，请重新生成绑定码。",
        }
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="identity.account_link_failed",
            target=f"person:{context.person_id}",
            status=status,
            risk_level="sensitive",
            detail=f"platform={context.platform}",
        )
        return IdentityCommandResult(
            context=context,
            response=responses.get(status, "账号绑定失败，请重新生成绑定码。"),
        )

    def _create_link_code(self, context: ChannelContext) -> str:
        code = self._generate_code()
        code_id = self.store.create_account_link_code(
            person_id=int(context.person_id),
            source_platform=context.platform,
            source_user_id=context.user_id,
            code_hash=self._hash_code(code),
        )
        self.store.add_audit_log(
            actor_source=context.source,
            actor_user_id=context.user_id,
            action="identity.link_code_created",
            target=f"person:{context.person_id}",
            status="ok",
            risk_level="sensitive",
            detail=f"link_code_id={code_id}; platform={context.platform}",
        )
        return (
            f"绑定码：{code}\n"
            "请在另一个平台的私聊中发送：绑定账号 "
            f"{code}\n绑定码 10 分钟内有效，且只能使用一次。"
        )

    @staticmethod
    def direct_conversation_id(person_id: int) -> str:
        return f"person:{person_id}:direct"

    @staticmethod
    def _parse_link_command(text: str) -> str | None:
        stripped = text.strip()
        lowered = stripped.lower()
        for prefix in _LINK_PREFIXES:
            lowered_prefix = prefix.lower()
            if lowered == lowered_prefix:
                return ""
            if lowered.startswith(lowered_prefix):
                suffix = stripped[len(prefix) :]
                if suffix and suffix[0] in " ：:":
                    return suffix.lstrip(" ：:")
        return None

    @staticmethod
    def _generate_code() -> str:
        characters = "".join(secrets.choice(_LINK_ALPHABET) for _ in range(12))
        return f"GB-{characters[:4]}-{characters[4:8]}-{characters[8:]}"

    @staticmethod
    def _normalize_code(value: str) -> str | None:
        normalized = value.strip().upper().replace(" ", "")
        parts = normalized.split("-")
        if len(parts) != 4 or parts[0] != "GB":
            return None
        if any(len(part) != 4 for part in parts[1:]):
            return None
        if any(character not in _LINK_ALPHABET for part in parts[1:] for character in part):
            return None
        return normalized

    @staticmethod
    def _hash_code(code: str) -> str:
        return hashlib.sha256(code.encode("ascii")).hexdigest()
