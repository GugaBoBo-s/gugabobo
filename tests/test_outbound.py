import json

from gugabobo.config import get_settings
from gugabobo.core.channel import ChannelContext
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.outbound import OutboundSkill


class FakeLLMClient:
    configured = True

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return self._payload


class DisabledLLMClient:
    configured = False

    def complete(self, messages):
        raise AssertionError("complete should not be called when not configured")


class FakeNapCatClient:
    def __init__(self, friends=None, fail_send=False, error_message="boom"):
        self._friends = friends or []
        self.fail_send = fail_send
        self.error_message = error_message
        self.sent = []

    def find_friends(self, target):
        query = target.strip().lower()
        return [
            friend
            for friend in self._friends
            if query in str(friend.get("remark", "")).lower()
            or query in str(friend.get("nickname", "")).lower()
        ]

    def send_private_msg(self, user_id, message):
        if self.fail_send:
            raise RuntimeError(self.error_message)
        self.sent.append((str(user_id), message))


def context(user_id="owner", conversation_id="qq:user:owner"):
    return ChannelContext(
        platform="qq",
        channel_type="private",
        source="qq_private",
        user_id=user_id,
        conversation_id=conversation_id,
        is_owner=True,
        is_wake_triggered=True,
    )


def skill(tmp_path, llm, napcat=None):
    store = MemoryStore(tmp_path / "outbound.db")
    return OutboundSkill(llm, store, napcat or FakeNapCatClient()), store


def send_payload(target, content):
    return json.dumps({"action": "send", "target": target, "content": content})


def test_plain_chat_and_disabled_llm_are_ignored(tmp_path):
    plain, _ = skill(
        tmp_path,
        FakeLLMClient(json.dumps({"action": "none", "target": "", "content": ""})),
    )
    assert plain.handle("今天天气怎么样", context()) is None

    disabled, _ = skill(tmp_path, DisabledLLMClient())
    assert disabled.handle("给kc说你好", context()) is None


def test_numeric_qq_requires_explicit_confirmation(tmp_path):
    napcat = FakeNapCatClient()
    outbound, store = skill(tmp_path, FakeLLMClient(send_payload("123456", "哈喽")), napcat)

    draft_reply = outbound.handle("给123456发哈喽", context())

    assert "草稿 #1" in draft_reply
    assert "确认发送 #1" in draft_reply
    assert napcat.sent == []
    assert store.get_outbound_draft(1)["status"] == "pending"

    sent_reply = outbound.handle("确认发送 #1", context())

    assert "已发送" in sent_reply
    assert napcat.sent == [("123456", "哈喽")]
    assert store.get_outbound_draft(1)["status"] == "sent"


def test_duplicate_or_foreign_confirmation_never_sends_twice(tmp_path):
    napcat = FakeNapCatClient()
    outbound, _ = skill(tmp_path, FakeLLMClient(send_payload("123", "hi")), napcat)
    outbound.handle("给123发hi", context())

    foreign = outbound.handle("确认发送 #1", context(user_id="other", conversation_id="qq:user:other"))
    first = outbound.handle("确认发送 #1", context())
    second = outbound.handle("确认发送 #1", context())

    assert "不属于" in foreign
    assert "已发送" in first
    assert "sent" in second
    assert napcat.sent == [("123", "hi")]


def test_unique_friend_is_resolved_before_draft(tmp_path):
    napcat = FakeNapCatClient(
        friends=[{"user_id": 2902808853, "remark": "kc", "nickname": "K.汤"}]
    )
    outbound, store = skill(
        tmp_path,
        FakeLLMClient(send_payload("kc", "你在干嘛")),
        napcat,
    )

    reply = outbound.handle("用QQ给kc说 你在干嘛", context())

    assert "kc（QQ 2902808853）" in reply
    assert store.get_outbound_draft(1)["recipient_user_id"] == "2902808853"
    assert napcat.sent == []


def test_missing_and_ambiguous_friends_do_not_create_draft(tmp_path):
    missing_client = FakeNapCatClient(
        friends=[{"user_id": 1, "remark": "kc", "nickname": "K"}]
    )
    missing, missing_store = skill(
        tmp_path,
        FakeLLMClient(send_payload("nobody", "hi")),
        missing_client,
    )
    assert "没有" in missing.handle("给nobody发hi", context())
    assert missing_store.list_outbound_drafts() == []

    ambiguous_client = FakeNapCatClient(
        friends=[
            {"user_id": 1, "remark": "kc", "nickname": "K.汤"},
            {"user_id": 2, "remark": "", "nickname": "kk"},
        ]
    )
    ambiguous, ambiguous_store = skill(
        tmp_path,
        FakeLLMClient(send_payload("k", "hi")),
        ambiguous_client,
    )
    reply = ambiguous.handle("给k发hi", context())
    assert "多个" in reply and "1" in reply and "2" in reply
    assert ambiguous_store.list_outbound_drafts() == []


def test_send_failure_is_terminal_and_audited(tmp_path):
    napcat = FakeNapCatClient(fail_send=True)
    outbound, store = skill(tmp_path, FakeLLMClient(send_payload("123", "hi")), napcat)
    outbound.handle("给123发hi", context())

    reply = outbound.handle("确认发送 #1", context())

    assert "失败" in reply
    assert store.get_outbound_draft(1)["status"] == "failed"
    assert store.list_audit_logs()[0]["status"] == "failed"


def test_send_failure_redacts_configured_access_token(tmp_path, monkeypatch):
    token = "napcat-private-token"
    monkeypatch.setenv("GUGABOBO_NAPCAT_ACCESS_TOKEN", token)
    get_settings.cache_clear()
    napcat = FakeNapCatClient(fail_send=True, error_message=f"request failed {token}")
    outbound, store = skill(tmp_path, FakeLLMClient(send_payload("123", "hi")), napcat)
    outbound.handle("给123发hi", context())

    reply = outbound.handle("确认发送 #1", context())

    assert token not in reply
    assert token not in store.list_audit_logs()[0]["detail"]
    assert "<redacted>" in reply
    get_settings.cache_clear()


def test_cancel_and_code_fence_parsing(tmp_path):
    payload = "```json\n" + send_payload("123", "hi") + "\n```"
    outbound, store = skill(tmp_path, FakeLLMClient(payload))
    outbound.handle("给123发hi", context())

    reply = outbound.handle("取消发送 #1", context())

    assert "已取消" in reply
    assert store.get_outbound_draft(1)["status"] == "cancelled"
