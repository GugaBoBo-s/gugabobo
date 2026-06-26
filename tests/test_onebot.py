from fastapi.testclient import TestClient

from gugabobo.adapters.onebot import OneBotMessageEvent, should_reply_to_event
from gugabobo.api.server import app
from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "onebot.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_NAPCAT_REPLY_ENABLED", "false")
    monkeypatch.setenv("GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED", "false")
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_private_message_event_allows_reply():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "你好",
            "message": "你好",
        }
    )

    assert should_reply_to_event(event, ["gugabobo"])
    assert event.source == "qq_private"
    assert event.text_content() == "你好"


def test_group_message_requires_mention_or_wake_word():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "group_id": 123,
            "user_id": 10001,
            "raw_message": "你好",
            "message": [{"type": "text", "data": {"text": "你好"}}],
        }
    )
    mentioned_event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "group_id": 123,
            "user_id": 10001,
            "raw_message": "@gugabobo 你好",
            "message": [
                {"type": "at", "data": {"qq": "999"}},
                {"type": "text", "data": {"text": " 你好"}},
            ],
        }
    )

    assert not should_reply_to_event(event, ["gugabobo"])
    assert should_reply_to_event(mentioned_event, ["gugabobo"])


def test_onebot_private_webhook_handles_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/onebot/v11/events",
        json={
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "你好",
            "message": "你好",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["sent"] is False
    assert response.json()["reply_available"] is True
    assert "reply" not in response.json()
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_onebot_private_webhook_can_return_passive_reply(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED", "true")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/onebot/v11/events",
        json={
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "你好",
            "message": "你好",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["passive_reply"] is True
    assert "已收到" in response.json()["reply"]
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_onebot_group_feedback_records_without_reply(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/onebot/v11/events",
        json={
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "group_id": 123,
            "user_id": 10001,
            "raw_message": "建议回复短一点",
            "message": [{"type": "text", "data": {"text": "建议回复短一点"}}],
        },
    )
    feedbacks_response = client.get("/feedbacks")

    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
    assert feedbacks_response.json()[0]["content"] == "建议回复短一点"
    get_settings.cache_clear()
    get_logger.cache_clear()
