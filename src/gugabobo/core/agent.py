from gugabobo.core.channel import ChannelContext
from gugabobo.core.access import context_access_role, role_can_use_skill
from gugabobo.core.persona import Persona
from gugabobo.core.router import Router
from gugabobo.config import Settings, get_settings
from gugabobo.infra.tokens import estimate_message_tokens
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill
from gugabobo.skills.feedback import FeedbackSkill
from gugabobo.skills.memory import MemorySkill
from gugabobo.skills.outbound import OutboundSkill
from gugabobo.skills.summarizer import SummarizerSkill


class CoreAgent:
    def __init__(
        self,
        store: MemoryStore,
        persona: Persona | None = None,
        router: Router | None = None,
    ) -> None:
        self.store = store
        self.persona = persona or Persona()
        self.router = router or Router()
        self.chat_skill = ChatSkill(self.persona)
        self.feedback_skill = FeedbackSkill(store)
        self.memory_skill = MemorySkill(store)
        self.outbound_skill = OutboundSkill(self.chat_skill.llm_client)
        self.summarizer_skill = SummarizerSkill(self.chat_skill.llm_client)

    def handle_message(
        self,
        text: str,
        source: str = "cli",
        user_id: str = "local",
        conversation_id: str | None = None,
    ) -> str:
        if source == "api":
            context = ChannelContext.api(user_id=user_id, conversation_id=conversation_id)
        elif source == "cli":
            context = ChannelContext.local(user_id=user_id, conversation_id=conversation_id)
        else:
            context = ChannelContext(
                platform="unknown",
                channel_type="unknown",
                source=source,
                user_id=user_id,
                conversation_id=conversation_id or f"{source}:{user_id}",
            )
        return self.handle_context_message(text, context)

    def handle_context_message(
        self,
        text: str,
        context: ChannelContext,
        images: list[str] | None = None,
    ) -> str:
        settings = get_settings()
        summary_row = self.store.get_conversation_summary(context.conversation_id)
        summarized_until = int(summary_row["updated_until_message_id"]) if summary_row else 0
        history = self.store.list_messages_after(
            context.conversation_id,
            after_message_id=summarized_until,
        )
        llm_history = self._trim_history_to_budget(
            [
                {"role": str(item["role"]), "content": str(item["content"])}
                for item in history
                if item["role"] in {"user", "assistant"}
            ],
            token_budget=settings.llm_history_token_budget,
        )
        system_context = self.build_system_context(
            conversation_id=context.conversation_id,
            memory_limit=settings.llm_memory_items,
        )
        stored_text = text
        if images:
            image_note = f"[图片x{len(images)}]"
            stored_text = f"{text} {image_note}".strip() if text else image_note
        self.store.add_message(
            source=context.source,
            user_id=context.user_id,
            role="user",
            content=stored_text,
            conversation_id=context.conversation_id,
        )
        route = self.router.route(text)
        access_role = context_access_role(context)
        if not role_can_use_skill(access_role, route.skill):
            response = self.permission_denied_response(route.skill, access_role)
        elif route.skill == "feedback":
            response = self.feedback_skill.record(
                text,
                source=context.source,
                user_id=context.user_id,
            )
        elif route.skill == "memory":
            response = self.memory_skill.record(text, subject=context.conversation_id)
        else:
            outbound_reply = None
            if access_role == "owner" and not images:
                outbound_reply = self.outbound_skill.handle(text)
            if outbound_reply is not None:
                response = outbound_reply
            else:
                response = self.chat_skill.reply(
                    text,
                    history=llm_history,
                    system_context=system_context,
                    images=images,
                )
        self.store.add_message(
            source=context.source,
            user_id="gugabobo",
            role="assistant",
            content=response,
            conversation_id=context.conversation_id,
        )
        self.maybe_summarize(context.conversation_id, settings)
        return response

    def _trim_history_to_budget(
        self,
        history: list[dict[str, str]],
        token_budget: int,
    ) -> list[dict[str, str]]:
        # Keep the most recent messages that fit within the token budget. Older
        # messages beyond the budget are dropped from the live window (they are
        # preserved in the rolling summary once maybe_summarize runs).
        if token_budget <= 0:
            return history
        kept: list[dict[str, str]] = []
        running = 0
        for item in reversed(history):
            running += estimate_message_tokens(item["role"], item["content"])
            if running > token_budget and kept:
                break
            kept.insert(0, item)
        return kept

    def maybe_summarize(self, conversation_id: str, settings: Settings) -> None:
        summary = self.store.get_conversation_summary(conversation_id)
        summarized_until = int(summary["updated_until_message_id"]) if summary else 0
        unsummarized = [
            item
            for item in self.store.list_messages_after(conversation_id, summarized_until)
            if item["role"] in {"user", "assistant"}
        ]
        if not unsummarized:
            return
        pending_tokens = sum(
            estimate_message_tokens(str(item["role"]), str(item["content"]))
            for item in unsummarized
        )
        # Only summarize when unsummarized content approaches the budget. Day-to-day
        # conversations stay well under this and are kept verbatim (ChatGPT-like).
        if pending_tokens < settings.llm_summary_trigger_tokens:
            return
        # Keep the most recent messages (by token budget) verbatim; summarize the
        # older remainder into the rolling summary.
        keep_tokens = settings.llm_summary_keep_recent_tokens
        kept: list[dict[str, object]] = []
        running = 0
        for item in reversed(unsummarized):
            running += estimate_message_tokens(str(item["role"]), str(item["content"]))
            if running > keep_tokens and kept:
                break
            kept.insert(0, item)
        keep_count = len(kept)
        batch = unsummarized[:-keep_count] if keep_count > 0 else unsummarized
        if not batch:
            return
        transcript = [
            {"role": str(item["role"]), "content": str(item["content"])}
            for item in batch
        ]
        previous = summary["summary"] if summary else ""
        new_summary = self.summarizer_skill.summarize(transcript, previous_summary=previous)
        if not new_summary:
            return
        self.store.upsert_conversation_summary(
            conversation_id=conversation_id,
            summary=new_summary,
            updated_until_message_id=int(batch[-1]["id"]),
        )

    def permission_denied_response(self, skill: str, role: str) -> str:
        if skill == "memory":
            return f"当前权限是 {role}，不能写入长期记忆。需要 trusted 或 owner。"
        if skill == "feedback":
            return f"当前权限是 {role}，不能记录反馈。需要 trusted 或 owner。"
        return f"当前权限是 {role}，不能执行这个操作。"

    def build_system_context(self, conversation_id: str, memory_limit: int) -> list[str]:
        context = []
        summary = self.store.get_conversation_summary(conversation_id)
        if summary:
            context.append(f"Conversation summary:\n{summary['summary']}")
        memory_items = self.store.list_memory_items(subject=conversation_id, limit=memory_limit)
        if memory_items:
            memory_lines = [
                f"- [{item['memory_type']}; importance={item['importance']}] {item['content']}"
                for item in memory_items
            ]
            context.append("Relevant long-term memories:\n" + "\n".join(memory_lines))
        return context

    def status(self) -> dict[str, object]:
        settings = get_settings()
        return {
            "name": self.persona.name,
            "status": "ready",
            "env": settings.env,
            "messages": self.store.count_messages(),
            "feedbacks": self.store.count_feedbacks(),
            "database": str(settings.db_path),
        }
