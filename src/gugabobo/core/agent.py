from gugabobo.core.channel import ChannelContext
from gugabobo.core.access import context_access_role, role_can_use_skill
from gugabobo.core.persona import Persona
from gugabobo.core.router import Router
from gugabobo.config import get_settings
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill
from gugabobo.skills.feedback import FeedbackSkill
from gugabobo.skills.memory import MemorySkill


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

    def handle_context_message(self, text: str, context: ChannelContext) -> str:
        settings = get_settings()
        history = self.store.list_conversation_messages(
            context.conversation_id,
            limit=settings.llm_context_messages,
        )
        llm_history = [
            {"role": str(item["role"]), "content": str(item["content"])}
            for item in history
            if item["role"] in {"user", "assistant"}
        ]
        system_context = self.build_system_context(
            conversation_id=context.conversation_id,
            memory_limit=settings.llm_memory_items,
        )
        self.store.add_message(
            source=context.source,
            user_id=context.user_id,
            role="user",
            content=text,
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
            response = self.chat_skill.reply(
                text,
                history=llm_history,
                system_context=system_context,
            )
        self.store.add_message(
            source=context.source,
            user_id="gugabobo",
            role="assistant",
            content=response,
            conversation_id=context.conversation_id,
        )
        return response

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
