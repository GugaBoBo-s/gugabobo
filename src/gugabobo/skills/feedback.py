from gugabobo.memory.store import MemoryStore


class FeedbackSkill:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def record(self, text: str, source: str, user_id: str) -> str:
        feedback_id = self.store.add_feedback(source=source, user_id=user_id, content=text)
        return f"已记录反馈 #{feedback_id}。"

