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


def test_private_message_event_builds_channel_context():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "你好",
            "message": "你好",
        }
    )

    context = event.to_channel_context(owner_ids={"10001"}, group_wake_words=["gugabobo"])

    assert context.platform == "qq"
    assert context.channel_type == "private"
    assert context.source == "qq_private"
    assert context.conversation_id == "qq:user:10001"
    assert context.is_owner is True
    assert context.is_wake_triggered is True


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


def test_group_message_event_builds_channel_context():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "group_id": 123,
            "user_id": 10001,
            "raw_message": "咕嘎BoBo 你好",
            "message": [{"type": "text", "data": {"text": "咕嘎BoBo 你好"}}],
        }
    )

    context = event.to_channel_context(owner_ids={"20002"}, group_wake_words=["咕嘎BoBo"])

    assert context.platform == "qq"
    assert context.channel_type == "group"
    assert context.source == "qq_group"
    assert context.user_id == "10001"
    assert context.group_id == "123"
    assert context.chat_id == "123"
    assert context.conversation_id == "qq:group:123"
    assert context.is_owner is False
    assert context.is_wake_triggered is True


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


def test_onebot_blocked_user_is_ignored(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/access-rules",
        json={"platform": "qq", "user_id": "10001", "role": "blocked"},
        headers={"X-Gugabobo-Admin-Token": "change-me"},
    )

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
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "blocked"
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_onebot_group_feedback_records_without_reply(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/access-rules",
        json={"platform": "qq", "user_id": "10001", "role": "trusted"},
        headers={"X-Gugabobo-Admin-Token": "change-me"},
    )

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


def test_onebot_user_role_cannot_record_group_feedback(tmp_path, monkeypatch):
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
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "insufficient role"
    assert feedbacks_response.json() == []
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_onebot_trusted_role_can_write_memory(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/access-rules",
        json={"platform": "qq", "user_id": "10001", "role": "trusted"},
        headers={"X-Gugabobo-Admin-Token": "change-me"},
    )

    response = client.post(
        "/onebot/v11/events",
        json={
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "记住我喜欢蓝色",
            "message": "记住我喜欢蓝色",
        },
    )
    memories_response = client.get("/memories?subject=qq:user:10001")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert memories_response.json()[0]["content"] == "我喜欢蓝色"
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_onebot_user_role_cannot_write_memory(tmp_path, monkeypatch):
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
            "raw_message": "记住我喜欢蓝色",
            "message": "记住我喜欢蓝色",
        },
    )
    memories_response = client.get("/memories?subject=qq:user:10001")

    assert response.status_code == 200
    assert "不能写入长期记忆" in response.json()["reply"]
    assert memories_response.json() == []
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_image_urls_extracted_from_message_segments():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "[CQ:image,file=abc.jpg,url=https://example.com/a.jpg]",
            "message": [
                {"type": "image", "data": {"url": "https://example.com/a.jpg"}},
            ],
        }
    )

    assert event.image_urls() == ["https://example.com/a.jpg"]
    assert event.text_content() == ""
    assert event.has_content() is True


def test_text_and_image_mixed_message():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "看这个 [CQ:image,url=https://example.com/a.jpg]",
            "message": [
                {"type": "text", "data": {"text": "看这个"}},
                {"type": "image", "data": {"url": "https://example.com/a.jpg"}},
            ],
        }
    )

    assert event.text_content() == "看这个"
    assert event.image_urls() == ["https://example.com/a.jpg"]


def test_raw_message_cq_codes_are_stripped_from_text():
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "你好[CQ:face,id=1]",
            "message": "你好[CQ:face,id=1]",
        }
    )

    assert event.text_content() == "你好"


def test_onebot_image_only_message_is_not_ignored(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED", "true")
    monkeypatch.setattr(
        "gugabobo.api.server.urls_to_data_uris",
        lambda urls: ["data:image/png;base64,Zm9v"],
    )
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/onebot/v11/events",
        json={
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "[CQ:image,url=https://example.com/a.jpg]",
            "message": [
                {"type": "image", "data": {"url": "https://example.com/a.jpg"}},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["passive_reply"] is True
    assert "图片" in body["reply"]
    get_settings.cache_clear()
    get_logger.cache_clear()
