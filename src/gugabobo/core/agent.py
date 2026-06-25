from gugabobo.core.persona import Persona
from gugabobo.core.router import Router
from gugabobo.config import get_settings
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill
from gugabobo.skills.feedback import FeedbackSkill


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

    def handle_message(self, text: str, source: str = "cli", user_id: str = "local") -> str:
        self.store.add_message(source=source, user_id=user_id, role="user", content=text)
        route = self.router.route(text)
        if route.skill == "feedback":
            response = self.feedback_skill.record(text, source=source, user_id=user_id)
        else:
            response = self.chat_skill.reply(text)
        self.store.add_message(source=source, user_id="gugabobo", role="assistant", content=response)
        return response

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
