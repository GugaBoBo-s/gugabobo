from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock

from gugabobo.core.access import context_access_role, role_can_use_skill
from gugabobo.core.channel import ChannelContext
from gugabobo.core.identity import IdentityService
from gugabobo.core.lifecycle import LifecycleError, PullRequestLifecycleService
from gugabobo.core.persona import Persona
from gugabobo.core.router import Router
from gugabobo.config import Settings, get_settings
from gugabobo.infra.logs import get_logger
from gugabobo.infra.tokens import estimate_message_tokens
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill
from gugabobo.skills.feedback import FeedbackSkill
from gugabobo.skills.memory import MemorySkill
from gugabobo.skills.outbound import OutboundSkill
from gugabobo.skills.summarizer import SummarizerSkill


_SUMMARY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gugabobo-summary")
_SUMMARY_CAPACITY = BoundedSemaphore(32)
_SUMMARY_LOCK = Lock()
_SUMMARY_IN_FLIGHT: set[str] = set()


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
        self.identity_service = IdentityService(store)
        self.outbound_skill = OutboundSkill(self.chat_skill.llm_client, store)
        self.summarizer_skill = SummarizerSkill(self.chat_skill.llm_client)
        self.lifecycle_service = PullRequestLifecycleService(store)
        self.background_summarize = False

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
        context = self.identity_service.resolve_context(context)
        identity_result = self.identity_service.handle_command(text, context)
        context = identity_result.context
        summary_row = self.store.get_conversation_summary(context.conversation_id)
        summarized_until = int(summary_row["updated_until_message_id"]) if summary_row else 0
        history = self.store.list_recent_messages_after(
            context.conversation_id,
            summarized_until,
            settings.llm_context_messages,
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
        access_role = context_access_role(context)
        route = self.router.route(text)
        if identity_result.response is not None:
            response = identity_result.response
        else:
            try:
                lifecycle_response = self.lifecycle_service.handle_command(text, context)
            except LifecycleError as error:
                lifecycle_response = f"PR 操作失败：{error}"
            if lifecycle_response is not None:
                response = lifecycle_response
            elif not role_can_use_skill(access_role, route.skill):
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
                    outbound_reply = self.outbound_skill.handle(text, context)
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
        self._run_summarize(context.conversation_id, settings)
        return response

    def _run_summarize(self, conversation_id: str, settings: Settings) -> None:
        if not self.background_summarize:
            self.maybe_summarize(conversation_id, settings)
            return
        with _SUMMARY_LOCK:
            if conversation_id in _SUMMARY_IN_FLIGHT:
                return
            if not _SUMMARY_CAPACITY.acquire(blocking=False):
                get_logger().warning("summary queue capacity reached")
                return
            _SUMMARY_IN_FLIGHT.add(conversation_id)
        try:
            _SUMMARY_EXECUTOR.submit(self._summary_worker, conversation_id, settings)
        except Exception:
            with _SUMMARY_LOCK:
                _SUMMARY_IN_FLIGHT.discard(conversation_id)
            _SUMMARY_CAPACITY.release()
            raise

    def _summary_worker(self, conversation_id: str, settings: Settings) -> None:
        try:
            self.maybe_summarize(conversation_id, settings)
        except Exception as exc:
            get_logger().warning("background summarize failed: %s", exc)
        finally:
            with _SUMMARY_LOCK:
                _SUMMARY_IN_FLIGHT.discard(conversation_id)
            _SUMMARY_CAPACITY.release()

    def _trim_history_to_budget(
        self,
        history: list[dict[str, str]],
        token_budget: int,
    ) -> list[dict[str, str]]:
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
        if pending_tokens < settings.llm_summary_trigger_tokens:
            return
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
