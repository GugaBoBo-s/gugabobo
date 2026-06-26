from fastapi.testclient import TestClient

from gugabobo.api.server import app
from gugabobo.config import get_settings


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_MOONSHOT_API_KEY", "")
    monkeypatch.setenv("GUGABOBO_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()


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
    assert data_response.status_code == 200
    assert "status" in data_response.json()
    assert "messages" in data_response.json()
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
