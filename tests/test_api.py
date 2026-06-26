from fastapi.testclient import TestClient

from gugabobo.api.server import app
from gugabobo.config import get_settings


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_CONFIG_FILE_PATH", str(tmp_path / ".env"))
    monkeypatch.setenv("GUGABOBO_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("GUGABOBO_LLM_PROVIDER", "moonshot")
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()


def admin_headers() -> dict[str, str]:
    return {"X-Gugabobo-Admin-Token": "test-admin"}


def test_health_endpoint(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    get_settings.cache_clear()


def test_chat_endpoint_records_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/chat", json={"message": "你好", "user_id": "u1"})
    status_response = client.get("/status")

    assert response.status_code == 200
    assert "已收到" in response.json()["reply"]
    assert status_response.json()["messages"] == 2
    get_settings.cache_clear()


def test_root_endpoint_returns_html(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "gugabobo" in response.text
    get_settings.cache_clear()


def test_dashboard_endpoints(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    page_response = client.get("/dashboard")
    data_response = client.get("/dashboard-data")

    assert page_response.status_code == 200
    assert "咕嘎BoBo Dashboard" in page_response.text
    assert "控制台" in page_response.text
    assert "编辑长期记忆" in page_response.text
    assert "配置编辑器" in page_response.text
    assert "会话上下文" in page_response.text
    assert "访问权限" in page_response.text
    assert "运行管理" in page_response.text
    assert "数据库表状态" in page_response.text
    assert "会话摘要" in page_response.text
    assert '""":' not in page_response.text
    assert data_response.status_code == 200
    assert "status" in data_response.json()
    assert "messages" in data_response.json()
    assert "table_counts" in data_response.json()
    assert "runtime" in data_response.json()
    assert data_response.json()["runtime"]["api"]["running"] is True
    get_settings.cache_clear()


def test_dashboard_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/chat", json={"message": "你好"})

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_runtime_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/runtime/telegram/start")

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_config_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/dashboard-control/config")

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_config_control_updates_env_file(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GUGABOBO_LLM_PROVIDER=moonshot\nGUGABOBO_DEEPSEEK_API_KEY=secret\n",
        encoding="utf-8",
    )
    client = TestClient(app)

    config_response = client.get("/dashboard-control/config", headers=admin_headers())
    update_response = client.post(
        "/dashboard-control/config",
        json={
            "values": {
                "GUGABOBO_LLM_PROVIDER": "deepseek",
                "GUGABOBO_LLM_CONTEXT_MESSAGES": 80,
                "GUGABOBO_TELEGRAM_REPLY_ENABLED": True,
                "GUGABOBO_DEEPSEEK_API_KEY": "should-not-save",
            }
        },
        headers=admin_headers(),
    )
    env_text = env_path.read_text(encoding="utf-8")

    assert config_response.status_code == 200
    assert config_response.json()["values"]["GUGABOBO_LLM_PROVIDER"] == "moonshot"
    assert update_response.status_code == 200
    assert "GUGABOBO_LLM_PROVIDER=deepseek" in env_text
    assert "GUGABOBO_LLM_CONTEXT_MESSAGES=80" in env_text
    assert "GUGABOBO_TELEGRAM_REPLY_ENABLED=true" in env_text
    assert "should-not-save" not in env_text
    assert "GUGABOBO_DEEPSEEK_API_KEY=secret" in env_text
    get_settings.cache_clear()


def test_dashboard_runtime_control_reports_unconfigured_telegram(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()
    client = TestClient(app)

    status_response = client.get("/runtime/status")
    start_response = client.post(
        "/dashboard-control/runtime/telegram/start",
        headers=admin_headers(),
    )

    assert status_response.status_code == 200
    assert status_response.json()["telegram_polling"]["configured"] is False
    assert start_response.json()["status"] == "not_configured"
    get_settings.cache_clear()


def test_dashboard_control_chat_records_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/dashboard-control/chat",
        json={"message": "你好", "conversation_id": "dashboard:test"},
        headers=admin_headers(),
    )
    messages_response = client.get("/messages")

    assert response.status_code == 200
    assert "已收到" in response.json()["reply"]
    assert messages_response.json()[0]["conversation_id"] == "dashboard:test"
    get_settings.cache_clear()


def test_dashboard_control_memory_summary_and_feedback(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    feedback_id = client.post(
        "/feedbacks",
        json={"content": "回复太长", "user_id": "u1"},
    ).json()["id"]

    memory_response = client.post(
        "/dashboard-control/memories",
        json={"subject": "global", "content": "主人喜欢短回复", "memory_type": "preference"},
        headers=admin_headers(),
    )
    summary_response = client.post(
        "/dashboard-control/summaries",
        json={"conversation_id": "dashboard:test", "summary": "正在测试控制台。"},
        headers=admin_headers(),
    )
    feedback_response = client.patch(
        f"/dashboard-control/feedbacks/{feedback_id}",
        json={"status": "triaged"},
        headers=admin_headers(),
    )

    assert memory_response.status_code == 200
    assert summary_response.json()["conversation_id"] == "dashboard:test"
    assert feedback_response.json()["status"] == "triaged"
    get_settings.cache_clear()


def test_memory_endpoint_filters_by_subject(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/memories",
        json={"subject": "telegram:user:1", "content": "TG 用户喜欢短回复"},
        headers=admin_headers(),
    )
    client.post(
        "/dashboard-control/memories",
        json={"subject": "qq:user:1", "content": "QQ 用户喜欢长回复"},
        headers=admin_headers(),
    )

    response = client.get("/memories?subject=telegram:user:1")

    contents = [item["content"] for item in response.json()]
    assert "TG 用户喜欢短回复" in contents
    assert "QQ 用户喜欢长回复" not in contents
    get_settings.cache_clear()


def test_dashboard_control_updates_and_deletes_memory(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    memory_id = client.post(
        "/dashboard-control/memories",
        json={"subject": "global", "content": "旧内容"},
        headers=admin_headers(),
    ).json()["id"]

    update_response = client.patch(
        f"/dashboard-control/memories/{memory_id}",
        json={
            "subject": "telegram:user:1",
            "content": "新内容",
            "memory_type": "preference",
            "importance": 9,
        },
        headers=admin_headers(),
    )
    filtered_response = client.get("/memories?subject=telegram:user:1")
    delete_response = client.delete(
        f"/dashboard-control/memories/{memory_id}",
        headers=admin_headers(),
    )
    after_delete_response = client.get("/memories?subject=telegram:user:1")

    assert update_response.status_code == 200
    assert filtered_response.json()[0]["content"] == "新内容"
    assert filtered_response.json()[0]["importance"] == 9
    assert delete_response.json()["deleted"] is True
    assert all(item["id"] != memory_id for item in after_delete_response.json())
    get_settings.cache_clear()


def test_message_endpoints(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    client.post("/chat", json={"message": "你好", "user_id": "u1"})
    messages_response = client.get("/messages")
    message_response = client.get("/messages/1")

    assert messages_response.status_code == 200
    assert len(messages_response.json()) == 2
    assert message_response.status_code == 200
    assert message_response.json()["content"] == "你好"
    get_settings.cache_clear()


def test_message_endpoint_filters_by_conversation(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    client.post("/chat", json={"message": "A", "user_id": "u1", "conversation_id": "api:a"})
    client.post("/chat", json={"message": "B", "user_id": "u2", "conversation_id": "api:b"})
    response = client.get("/messages?conversation_id=api:a")

    contents = [item["content"] for item in response.json()]
    assert "A" in contents
    assert "B" not in contents
    get_settings.cache_clear()


def test_dashboard_control_clears_conversation_messages_and_deletes_summary(
    tmp_path,
    monkeypatch,
):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/dashboard-control/chat",
        json={"message": "你好", "conversation_id": "dashboard:test"},
        headers=admin_headers(),
    )
    client.post(
        "/dashboard-control/summaries",
        json={"conversation_id": "dashboard:test", "summary": "测试摘要"},
        headers=admin_headers(),
    )

    clear_response = client.delete(
        "/dashboard-control/conversations/dashboard:test/messages",
        headers=admin_headers(),
    )
    messages_response = client.get("/messages?conversation_id=dashboard:test")
    delete_summary_response = client.delete(
        "/dashboard-control/summaries/dashboard:test",
        headers=admin_headers(),
    )

    assert clear_response.json()["deleted"] == 2
    assert messages_response.json() == []
    assert delete_summary_response.json()["deleted"] is True
    get_settings.cache_clear()


def test_dashboard_control_manages_access_rules(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    create_response = client.post(
        "/dashboard-control/access-rules",
        json={
            "platform": "telegram",
            "user_id": "10001",
            "role": "blocked",
            "display_name": "blocked user",
            "notes": "spam",
        },
        headers=admin_headers(),
    )
    rules_response = client.get("/access-rules")
    delete_response = client.delete(
        f"/dashboard-control/access-rules/{create_response.json()['id']}",
        headers=admin_headers(),
    )

    assert create_response.status_code == 200
    assert rules_response.json()[0]["role"] == "blocked"
    assert rules_response.json()[0]["notes"] == "spam"
    assert delete_response.json()["deleted"] is True
    get_settings.cache_clear()


def test_feedback_status_endpoint(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    create_response = client.post("/feedbacks", json={"content": "回复太长", "user_id": "u1"})
    feedback_id = create_response.json()["id"]
    update_response = client.patch(f"/feedbacks/{feedback_id}", json={"status": "resolved"})
    feedbacks_response = client.get("/feedbacks")

    assert update_response.status_code == 200
    assert update_response.json()["status"] == "resolved"
    assert feedbacks_response.json()[0]["status"] == "resolved"
    get_settings.cache_clear()
