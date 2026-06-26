from fastapi.testclient import TestClient

from gugabobo.adapters.telegram import TelegramMessageEvent
from gugabobo.adapters.telegram_runtime import handle_telegram_update
from gugabobo.api.server import app
from gugabobo.config import get_settings
from gugabobo.infra.runtime import build_agent
from gugabobo.infra.logs import get_logger


class FakeTelegramClient:
    def __init__(self):
        self.sent_messages = []

    def send_message(self, chat_id: str, text: str) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text})


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "telegram.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("GUGABOBO_TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("GUGABOBO_TELEGRAM_REPLY_ENABLED", "false")
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    get_logger.cache_clear()


def private_payload(text: str = "你好") -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": 10001, "username": "owner"},
            "chat": {"id": 10001, "type": "private"},
            "text": text,
        },
    }


def group_payload(text: str = "你好") -> dict[str, object]:
    return {
        "update_id": 2,
        "message": {
            "message_id": 20,
            "from": {"id": 10001, "username": "member"},
            "chat": {"id": -100123, "type": "supergroup", "title": "test"},
            "text": text,
        },
    }


def test_private_message_event_builds_channel_context():
    event = TelegramMessageEvent.from_payload(private_payload())

    context = event.to_channel_context(owner_ids={"10001"}, group_wake_words=["咕嘎BoBo"])

    assert context.platform == "telegram"
    assert context.channel_type == "private"
    assert context.source == "telegram_private"
    assert context.user_id == "10001"
    assert context.chat_id == "10001"
    assert context.conversation_id == "telegram:user:10001"
    assert context.is_owner is True
    assert context.is_wake_triggered is True


def test_group_message_event_builds_channel_context():
    event = TelegramMessageEvent.from_payload(group_payload("咕嘎BoBo 你好"))

    context = event.to_channel_context(owner_ids=set(), group_wake_words=["咕嘎BoBo"])

    assert context.platform == "telegram"
    assert context.channel_type == "group"
    assert context.source == "telegram_group"
    assert context.user_id == "10001"
    assert context.group_id == "-100123"
    assert context.chat_id == "-100123"
    assert context.conversation_id == "telegram:group:-100123"
    assert context.is_wake_triggered is True


def test_telegram_private_webhook_handles_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/telegram/events", json=private_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["sent"] is False
    assert response.json()["reply_available"] is True
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_group_message_requires_wake_word(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/telegram/events", json=group_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "reply not allowed"
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_group_wake_word_handles_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/telegram/events", json=group_payload("咕嘎BoBo 你好"))
    messages_response = client.get("/messages")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert messages_response.json()[0]["conversation_id"] == "telegram:group:-100123"
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_webhook_secret_is_checked(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_TELEGRAM_WEBHOOK_SECRET", "secret")
    get_settings.cache_clear()
    client = TestClient(app)

    rejected = client.post("/telegram/events", json=private_payload())
    accepted = client.post(
        "/telegram/events",
        json=private_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_runtime_can_send_reply(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    client = FakeTelegramClient()

    result = handle_telegram_update(
        private_payload(),
        agent=build_agent(),
        settings=settings,
        send_reply=True,
        client=client,
    )

    assert result["status"] == "ok"
    assert result["sent"] is True
    assert client.sent_messages[0]["chat_id"] == "10001"
    assert "已收到" in client.sent_messages[0]["text"]
    get_settings.cache_clear()
    get_logger.cache_clear()
