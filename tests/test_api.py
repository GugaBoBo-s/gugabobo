from fastapi.testclient import TestClient

from gugabobo.api.server import app


def test_health_endpoint():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_records_message(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(db_path))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))

    from gugabobo.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post("/chat", json={"message": "你好", "user_id": "u1"})
    status_response = client.get("/status")

    assert response.status_code == 200
    assert "已收到" in response.json()["reply"]
    assert status_response.json()["messages"] == 2
    get_settings.cache_clear()

