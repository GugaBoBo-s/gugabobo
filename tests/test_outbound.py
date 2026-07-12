import json

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

    def complete(self, messages):  # pragma: no cover - should not be called
        raise AssertionError("complete should not be called when not configured")


class FakeNapCatClient:
    def __init__(self, friends=None, fail_send=False):
        self._friends = friends or []
        self.fail_send = fail_send
        self.sent = []

    def find_friends(self, target):
        query = target.strip().lower()
        return [
            f
            for f in self._friends
            if query in str(f.get("remark", "")).lower()
            or query in str(f.get("nickname", "")).lower()
        ]

    def send_private_msg(self, user_id, message):
        if self.fail_send:
            raise RuntimeError("boom")
        self.sent.append((str(user_id), message))


def _send_payload(target, content):
    return json.dumps({"action": "send", "target": target, "content": content})


def test_parse_intent_returns_none_for_plain_chat():
    llm = FakeLLMClient(json.dumps({"action": "none", "target": "", "content": ""}))
    skill = OutboundSkill(llm, FakeNapCatClient())

    assert skill.handle("今天天气怎么样") is None


def test_parse_intent_ignored_when_llm_not_configured():
    skill = OutboundSkill(DisabledLLMClient(), FakeNapCatClient())

    assert skill.handle("给kc说你好") is None


def test_send_to_numeric_qq_directly():
    llm = FakeLLMClient(_send_payload("123456", "哈喽"))
    napcat = FakeNapCatClient()
    skill = OutboundSkill(llm, napcat)

    reply = skill.handle("给123456发哈喽")

    assert napcat.sent == [("123456", "哈喽")]
    assert "已发送" in reply


def test_send_to_unique_friend_by_remark():
    llm = FakeLLMClient(_send_payload("kc", "你在干嘛"))
    napcat = FakeNapCatClient(
        friends=[{"user_id": 2902808853, "remark": "kc", "nickname": "K.汤"}]
    )
    skill = OutboundSkill(llm, napcat)

    reply = skill.handle("用QQ给kc说 你在干嘛")

    assert napcat.sent == [("2902808853", "你在干嘛")]
    assert "已发送" in reply


def test_no_match_asks_for_qq():
    llm = FakeLLMClient(_send_payload("nobody", "hi"))
    napcat = FakeNapCatClient(friends=[{"user_id": 1, "remark": "kc", "nickname": "K"}])
    skill = OutboundSkill(llm, napcat)

    reply = skill.handle("给nobody发hi")

    assert napcat.sent == []
    assert "没有" in reply and "QQ" in reply


def test_multiple_matches_lists_candidates():
    llm = FakeLLMClient(_send_payload("k", "hi"))
    napcat = FakeNapCatClient(
        friends=[
            {"user_id": 1, "remark": "kc", "nickname": "K.汤"},
            {"user_id": 2, "remark": "", "nickname": "kk"},
        ]
    )
    skill = OutboundSkill(llm, napcat)

    reply = skill.handle("给k发hi")

    assert napcat.sent == []
    assert "多个" in reply
    assert "1" in reply and "2" in reply


def test_send_failure_reported():
    llm = FakeLLMClient(_send_payload("123", "hi"))
    napcat = FakeNapCatClient(fail_send=True)
    skill = OutboundSkill(llm, napcat)

    reply = skill.handle("给123发hi")

    assert "失败" in reply


def test_intent_parsing_strips_code_fence():
    payload = "```json\n" + _send_payload("123", "hi") + "\n```"
    llm = FakeLLMClient(payload)
    napcat = FakeNapCatClient()
    skill = OutboundSkill(llm, napcat)

    reply = skill.handle("给123发hi")

    assert napcat.sent == [("123", "hi")]
    assert "已发送" in reply
