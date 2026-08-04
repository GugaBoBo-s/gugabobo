import asyncio

from fastapi.testclient import TestClient
from aiogram.types import Update

from gugabobo.adapters.telegram import TelegramIncomingMessage
from gugabobo.adapters.telegram_runtime import TelegramService
from gugabobo.api.server import app
from gugabobo.config import get_settings
from gugabobo.infra.runtime import build_agent
from gugabobo.infra.logs import get_logger


class FakeTelegramClient:
    configured = False

    def __init__(self):
        self.sent_messages = []
        self.bot = object()

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> None:
        self.sent_messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )

    async def close(self) -> None:
        return None


class FlakyTelegramClient(FakeTelegramClient):
    configured = False

    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> None:
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("temporary send failure")
        await super().send_message(chat_id, text, reply_markup)


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "telegram.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("GUGABOBO_TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("GUGABOBO_TELEGRAM_REPLY_ENABLED", "false")
    monkeypatch.setenv("GUGABOBO_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    get_logger.cache_clear()


def process_payload(payload, agent, settings, send_reply, client):
    service = TelegramService(
        agent=agent,
        settings=settings,
        send_replies=send_reply,
        client=client,
    )
    return asyncio.run(service.process_update(Update.model_validate(payload)))


def private_payload(text: str = "你好") -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": 1,
            "from": {
                "id": 10001,
                "is_bot": False,
                "first_name": "owner",
                "username": "owner",
            },
            "chat": {"id": 10001, "type": "private"},
            "text": text,
        },
    }


def group_payload(text: str = "你好") -> dict[str, object]:
    return {
        "update_id": 2,
        "message": {
            "message_id": 20,
            "date": 1,
            "from": {
                "id": 10001,
                "is_bot": False,
                "first_name": "member",
                "username": "member",
            },
            "chat": {"id": -100123, "type": "supergroup", "title": "test"},
            "text": text,
        },
    }


def test_private_message_event_builds_channel_context():
    event = TelegramIncomingMessage.from_update(Update.model_validate(private_payload()))
    assert event is not None

    context = event.to_channel_context(
        owner_ids={"10001"},
        group_wake_words=["咕嘎BoBo"],
        bot_username="",
    )

    assert context.platform == "telegram"
    assert context.channel_type == "private"
    assert context.source == "telegram_private"
    assert context.user_id == "10001"
    assert context.chat_id == "10001"
    assert context.conversation_id == "telegram:user:10001"
    assert context.is_owner is True
    assert context.is_wake_triggered is True


def test_group_message_event_builds_channel_context():
    event = TelegramIncomingMessage.from_update(
        Update.model_validate(group_payload("咕嘎BoBo 你好"))
    )
    assert event is not None

    context = event.to_channel_context(
        owner_ids=set(),
        group_wake_words=["咕嘎BoBo"],
        bot_username="",
    )

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


def test_community_command_returns_configured_links(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()

    result = process_payload(
        private_payload("/community"),
        agent=build_agent(),
        settings=settings,
        send_reply=False,
        client=FakeTelegramClient(),
    )

    assert result["community_links"] == {
        "group": "https://t.me/ScarletKc_Group",
        "bot": "https://t.me/FogMoeBot",
        "channel": "https://t.me/FOG_MOE",
        "summary_bot": "https://t.me/rigerubot?startgroup=true",
        "developer_gugabobo": "https://t.me/woshigugabobo",
        "developer_scarletkc": "https://t.me/scarletkc",
        "github_scarletkc": "https://github.com/scarletkc",
        "github_fogmoe": "https://github.com/FogMoe",
        "github_geyugong": "https://github.com/orgs/FogMoe/people/GeYugong",
        "github_gugabobo": "https://github.com/GugaBoBo-s",
    }
    assert result["sent"] is False
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_fogmoe_command_sends_inline_keyboard(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    client = FakeTelegramClient()

    result = process_payload(
        private_payload("/fogmoe"),
        agent=build_agent(),
        settings=settings,
        send_reply=True,
        client=client,
    )

    keyboard = client.sent_messages[0]["reply_markup"]
    urls = [row[0].url for row in keyboard.inline_keyboard]
    assert urls == [
        "https://t.me/ScarletKc_Group",
        "https://t.me/FogMoeBot",
        "https://t.me/FOG_MOE",
        "https://t.me/rigerubot?startgroup=true",
        "https://t.me/woshigugabobo",
        "https://t.me/scarletkc",
        "https://github.com/scarletkc",
        "https://github.com/FogMoe",
        "https://github.com/orgs/FogMoe/people/GeYugong",
        "https://github.com/GugaBoBo-s",
    ]
    assert result["sent"] is True
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_summary_command_mentions_rigerubot(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    client = FakeTelegramClient()

    result = process_payload(
        group_payload("/summary@GugaBoBoBot 100"),
        agent=build_agent(),
        settings=settings,
        send_reply=True,
        client=client,
    )

    message = client.sent_messages[0]
    assert "@rigerubot" in message["text"]
    assert message["reply_markup"].inline_keyboard[0][0].url == (
        "https://t.me/rigerubot?startgroup=true"
    )
    assert result["summary_bot"] == "@rigerubot"
    assert result["sent"] is True
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_developers_command_returns_both_accounts(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    client = FakeTelegramClient()

    result = process_payload(
        private_payload("/developers"),
        agent=build_agent(),
        settings=settings,
        send_reply=True,
        client=client,
    )

    assert result["developers"] == {
        "@woshigugabobo": "https://t.me/woshigugabobo",
        "@scarletkc": "https://t.me/scarletkc",
    }
    assert "@woshigugabobo" in client.sent_messages[0]["text"]
    assert "@scarletkc" in client.sent_messages[0]["text"]
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_github_command_returns_all_related_accounts(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    client = FakeTelegramClient()

    result = process_payload(
        private_payload("/github"),
        agent=build_agent(),
        settings=settings,
        send_reply=True,
        client=client,
    )

    assert result["github_links"] == {
        "ScarletKC": "https://github.com/scarletkc",
        "FogMoe": "https://github.com/FogMoe",
        "GeYugong": "https://github.com/orgs/FogMoe/people/GeYugong",
        "GugaBoBo-s": "https://github.com/GugaBoBo-s",
    }
    assert len(client.sent_messages[0]["reply_markup"].inline_keyboard) == 4
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


def test_telegram_owner_merge_command_bypasses_group_wake_word(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_OWNER_TELEGRAM_IDS", "10001")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post("/telegram/events", json=group_payload("同意合并 PR #15"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    messages = client.get("/messages").json()
    assert messages[0]["content"].startswith("PR 操作失败：")
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_user_role_cannot_record_group_feedback(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/telegram/events", json=group_payload("建议回复短一点"))
    feedbacks_response = client.get("/feedbacks")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "insufficient role"
    assert feedbacks_response.json() == []
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_trusted_role_can_record_group_feedback(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/access-rules",
        json={"platform": "telegram", "user_id": "10001", "role": "trusted"},
        headers={"X-Gugabobo-Admin-Token": "test-admin"},
    )

    response = client.post("/telegram/events", json=group_payload("建议回复短一点"))
    feedbacks_response = client.get("/feedbacks")

    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
    assert feedbacks_response.json()[0]["content"] == "建议回复短一点"
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


def test_telegram_user_role_cannot_write_memory(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/telegram/events", json=private_payload("记住我喜欢蓝色"))
    memories_response = client.get("/memories?subject=telegram:user:10001")

    assert response.status_code == 200
    assert response.json()["reply_available"] is True
    assert memories_response.json() == []
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_trusted_role_can_write_memory(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/access-rules",
        json={"platform": "telegram", "user_id": "10001", "role": "trusted"},
        headers={"X-Gugabobo-Admin-Token": "test-admin"},
    )

    response = client.post("/telegram/events", json=private_payload("记住我喜欢蓝色"))
    memories_response = client.get("/memories?subject=telegram:user:10001")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert memories_response.json()[0]["content"] == "我喜欢蓝色"
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_telegram_blocked_user_is_ignored(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/access-rules",
        json={"platform": "telegram", "user_id": "10001", "role": "blocked"},
        headers={"X-Gugabobo-Admin-Token": "test-admin"},
    )

    response = client.post("/telegram/events", json=private_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "blocked"
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

    result = process_payload(
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


def test_telegram_retry_reuses_reply_without_reprocessing(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    agent = build_agent(background_summarize=False)
    client = FlakyTelegramClient()

    try:
        process_payload(
            private_payload(),
            agent=agent,
            settings=settings,
            send_reply=True,
            client=client,
        )
    except RuntimeError:
        pass

    assert agent.store.count_messages() == 2
    assert agent.store.get_inbound_event("telegram", "1")["status"] == "reply_ready"

    retry = process_payload(
        private_payload(),
        agent=agent,
        settings=settings,
        send_reply=True,
        client=client,
    )
    duplicate = process_payload(
        private_payload(),
        agent=agent,
        settings=settings,
        send_reply=True,
        client=client,
    )

    assert retry == {"status": "ok", "sent": True}
    assert duplicate["duplicate"] is True
    assert agent.store.count_messages() == 2
    assert client.attempts == 2
    get_settings.cache_clear()
    get_logger.cache_clear()


def photo_private_payload(caption: str | None = None) -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": 30,
        "date": 1,
        "from": {
            "id": 10001,
            "is_bot": False,
            "first_name": "owner",
            "username": "owner",
        },
        "chat": {"id": 10001, "type": "private"},
        "photo": [
            {
                "file_id": "small_id",
                "file_unique_id": "small_unique_id",
                "width": 90,
                "height": 90,
            },
            {
                "file_id": "large_id",
                "file_unique_id": "large_unique_id",
                "width": 800,
                "height": 800,
            },
        ],
    }
    if caption is not None:
        message["caption"] = caption
    return {"update_id": 3, "message": message}


class ImageCapableFakeClient:
    configured = True

    def __init__(self):
        self.sent_messages = []
        self.downloaded_ids = []

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text})

    async def file_ids_to_data_uris(self, file_ids, timeout: float = 20.0):
        self.downloaded_ids.extend(file_ids)
        return [f"data:image/jpeg;base64,fake-{fid}" for fid in file_ids]


def test_photo_event_extracts_largest_file_id():
    event = TelegramIncomingMessage.from_update(
        Update.model_validate(photo_private_payload())
    )
    assert event is not None

    assert event.photo_file_ids == ("large_id",)
    assert event.has_content() is True


def test_photo_caption_becomes_text():
    event = TelegramIncomingMessage.from_update(
        Update.model_validate(photo_private_payload(caption="这是什么"))
    )
    assert event is not None

    assert event.text == "这是什么"
    assert event.photo_file_ids == ("large_id",)


def test_photo_only_private_message_triggers_reply():
    event = TelegramIncomingMessage.from_update(
        Update.model_validate(photo_private_payload())
    )
    assert event is not None

    context = event.to_channel_context(
        owner_ids=set(),
        group_wake_words=[],
        bot_username="",
    )
    assert context.is_wake_triggered is True


def test_telegram_runtime_downloads_and_passes_images(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    settings = get_settings()
    client = ImageCapableFakeClient()

    result = process_payload(
        photo_private_payload(caption="看看这个"),
        agent=build_agent(),
        settings=settings,
        send_reply=True,
        client=client,
    )

    assert result["status"] == "ok"
    assert result["sent"] is True
    assert client.downloaded_ids == ["large_id"]
    get_settings.cache_clear()
    get_logger.cache_clear()


def test_bytes_to_data_uri_detects_png():
    from gugabobo.infra.images import bytes_to_data_uri

    png_header = b"\x89PNG\r\n\x1a\n" + b"rest"
    result = bytes_to_data_uri(png_header)

    assert result is not None
    assert result.startswith("data:image/png;base64,")
    assert bytes_to_data_uri(b"") is None
