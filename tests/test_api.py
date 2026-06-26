from fastapi.testclient import TestClient

from gugabobo.api.server import app
from gugabobo.config import get_settings


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_ADMIN_TOKEN", "test-admin")
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
    assert "数据库表状态" in page_response.text
    assert "会话摘要" in page_response.text
    assert '""":' not in page_response.text
    assert data_response.status_code == 200
    assert "status" in data_response.json()
    assert "messages" in data_response.json()
    assert "table_counts" in data_response.json()
    get_settings.cache_clear()


def test_dashboard_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/chat", json={"message": "你好"})

    assert response.status_code == 401
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
