from gugabobo.core.agent import CoreAgent
from gugabobo.memory.store import MemoryStore


def test_chat_records_messages(tmp_path):
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    reply = agent.handle_message("你好", source="test", user_id="u1")

    assert "已收到" in reply
    assert agent.store.count_messages() == 2


def test_feedback_route_records_feedback(tmp_path):
    agent = CoreAgent(MemoryStore(tmp_path / "test.db"))

    reply = agent.handle_message("建议回复短一点", source="test", user_id="u1")

    assert "已记录反馈" in reply
    assert agent.store.count_feedbacks() == 1

