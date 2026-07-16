import re

from gugabobo.core.access import evaluate_access
from gugabobo.core.agent import CoreAgent
from gugabobo.core.channel import ChannelContext
from gugabobo.core.identity import IdentityService
from gugabobo.core.persona import Persona
from gugabobo.memory.store import MemoryStore
from gugabobo.skills.chat import ChatSkill


class HistoryCapturingLLMClient:
    configured = True

    def __init__(self):
        self.histories = []

    def chat(self, text, persona, history=None, system_context=None, images=None):
        self.histories.append(history or [])
        return type("Result", (), {"content": f"reply: {text}", "model": "test-model"})()


def private_context(platform: str, user_id: str, is_owner: bool = False) -> ChannelContext:
    source = "qq_private" if platform == "qq" else "telegram_private"
    return ChannelContext(
        platform=platform,
        channel_type="private",
        source=source,
        user_id=user_id,
        conversation_id=f"{platform}:user:{user_id}",
        chat_id=user_id,
        is_owner=is_owner,
        is_wake_triggered=True,
    )


def test_unlinked_accounts_resolve_to_separate_people(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    identity = IdentityService(store)

    qq = identity.resolve_context(private_context("qq", "10001"))
    telegram = identity.resolve_context(private_context("telegram", "20002"))

    assert qq.person_id is not None
    assert telegram.person_id is not None
    assert qq.person_id != telegram.person_id
    assert qq.conversation_id == f"person:{qq.person_id}:direct"
    assert telegram.conversation_id == f"person:{telegram.person_id}:direct"


def test_group_context_keeps_group_conversation_isolated(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    identity = IdentityService(store)
    context = ChannelContext(
        platform="qq",
        channel_type="group",
        source="qq_group",
        user_id="10001",
        conversation_id="qq:group:30003",
        group_id="30003",
        chat_id="30003",
        is_wake_triggered=True,
    )

    resolved = identity.resolve_context(context)

    assert resolved.person_id is not None
    assert resolved.conversation_id == "qq:group:30003"


def test_cross_platform_link_shares_private_history(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    agent = CoreAgent(store)
    llm_client = HistoryCapturingLLMClient()
    agent.chat_skill = ChatSkill(Persona(), llm_client=llm_client)

    agent.handle_context_message("我叫小顾", private_context("qq", "10001"))
    link_reply = agent.handle_context_message("绑定账号", private_context("qq", "10001"))
    code = re.search(r"GB-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", link_reply).group(0)
    result = agent.handle_context_message(
        f"绑定账号 {code}",
        private_context("telegram", "20002"),
    )
    agent.handle_context_message("我叫什么？", private_context("telegram", "20002"))

    qq_account = store.get_channel_account("qq", "10001")
    telegram_account = store.get_channel_account("telegram", "20002")
    assert "绑定成功" in result
    assert qq_account["person_id"] == telegram_account["person_id"]
    assert any(item["content"] == "我叫小顾" for item in llm_client.histories[-1])


def test_link_code_is_hashed_and_single_use(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    agent = CoreAgent(store)

    link_reply = agent.handle_context_message("绑定账号", private_context("qq", "10001"))
    code = re.search(r"GB-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", link_reply).group(0)
    with store.connect() as conn:
        stored = conn.execute("SELECT code_hash FROM account_link_codes").fetchone()

    first = agent.handle_context_message(
        f"绑定账号 {code}",
        private_context("telegram", "20002"),
    )
    second = agent.handle_context_message(
        f"绑定账号 {code}",
        private_context("telegram", "30003"),
    )

    assert stored["code_hash"] != code
    assert "绑定成功" in first
    assert "无效或已经使用" in second


def test_linked_owner_role_is_available_on_other_platform(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    agent = CoreAgent(store)
    qq_context = private_context("qq", "10001", is_owner=True)

    link_reply = agent.handle_context_message("绑定账号", qq_context)
    code = re.search(r"GB-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", link_reply).group(0)
    telegram_context = private_context("telegram", "20002")
    agent.handle_context_message(f"绑定账号 {code}", telegram_context)

    access = evaluate_access(telegram_context, store)
    assert access.allowed is True
    assert access.role == "owner"


def test_legacy_private_context_is_migrated_and_remains_queryable(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    store.add_message(
        source="qq_private",
        user_id="10001",
        role="user",
        content="旧消息",
        conversation_id="qq:user:10001",
    )
    store.add_memory_item(
        subject="qq:user:10001",
        content="旧记忆",
        memory_type="preference",
    )
    store.upsert_conversation_summary("qq:user:10001", "旧摘要", 1)

    resolved = IdentityService(store).resolve_context(private_context("qq", "10001"))

    canonical_messages = store.list_conversation_messages(resolved.conversation_id)
    legacy_messages = store.list_conversation_messages("qq:user:10001")
    legacy_memories = store.list_memory_items(subject="qq:user:10001")
    legacy_summary = store.get_conversation_summary("qq:user:10001")
    assert canonical_messages[0]["content"] == "旧消息"
    assert legacy_messages == canonical_messages
    assert legacy_memories[0]["content"] == "旧记忆"
    assert legacy_summary["summary"] == "旧摘要"


def test_expired_link_code_cannot_merge_accounts(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    agent = CoreAgent(store)

    link_reply = agent.handle_context_message("绑定账号", private_context("qq", "10001"))
    code = re.search(r"GB-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", link_reply).group(0)
    with store.connect() as conn:
        conn.execute(
            "UPDATE account_link_codes SET expires_at = datetime('now', '-1 minute')"
        )

    response = agent.handle_context_message(
        f"绑定账号 {code}",
        private_context("telegram", "20002"),
    )

    qq_account = store.get_channel_account("qq", "10001")
    telegram_account = store.get_channel_account("telegram", "20002")
    assert "已经过期" in response
    assert qq_account["person_id"] != telegram_account["person_id"]
