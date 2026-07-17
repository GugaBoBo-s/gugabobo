from fastapi.testclient import TestClient

from gugabobo.api.server import app
from gugabobo.config import get_settings


def configure_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUGABOBO_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("GUGABOBO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GUGABOBO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GUGABOBO_CONFIG_FILE_PATH", str(tmp_path / ".env"))
    monkeypatch.setenv("GUGABOBO_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("GUGABOBO_NAPCAT_DIR", str(tmp_path / "napcat"))
    monkeypatch.setenv("GUGABOBO_LLM_PROVIDER", "moonshot")
    monkeypatch.setenv("GUGABOBO_TELEGRAM_BOT_TOKEN", "")
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
    assert "QQ/NapCat 诊断" in page_response.text
    assert "Telegram 诊断" in page_response.text
    assert "启动 NapCat" in page_response.text
    assert "打开 NapCat WebUI" in page_response.text
    assert "会话上下文" in page_response.text
    assert "访问权限" in page_response.text
    assert "运行管理" in page_response.text
    assert "数据库表状态" in page_response.text
    assert "会话摘要" in page_response.text
    assert "审计日志" in page_response.text
    assert "合并授权" in page_response.text
    assert "改进反思" in page_response.text
    assert "部署记录" in page_response.text
    assert "主人通知" in page_response.text
    assert '""":' not in page_response.text
    assert data_response.status_code == 200
    assert "status" in data_response.json()
    assert "messages" in data_response.json()
    assert "table_counts" in data_response.json()
    assert "audit_logs" in data_response.json()
    assert "runtime" in data_response.json()
    assert "qq_diagnostics" in data_response.json()
    assert "telegram_diagnostics" in data_response.json()
    assert "merge_authorizations" in data_response.json()
    assert "improvement_reflections" in data_response.json()
    assert "deployment_records" in data_response.json()
    assert "owner_notifications" in data_response.json()
    assert data_response.json()["runtime"]["api"]["running"] is True
    get_settings.cache_clear()


def test_dashboard_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/chat", json={"message": "你好"})

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_control_rejects_unsafe_admin_token_configuration(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    for token in ("", "change-me"):
        monkeypatch.setenv("GUGABOBO_ADMIN_TOKEN", token)
        get_settings.cache_clear()
        client = TestClient(app)

        response = client.post(
            "/dashboard-control/chat",
            json={"message": "你好"},
            headers={"X-Gugabobo-Admin-Token": token},
        )

        assert response.status_code == 503
    get_settings.cache_clear()


def test_dashboard_runtime_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/runtime/telegram/start")

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_napcat_runtime_control_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/runtime/napcat/start")

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_napcat_runtime_control_reports_missing_directory(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    status_response = client.get("/runtime/status")
    start_response = client.post(
        "/dashboard-control/runtime/napcat/start",
        headers=admin_headers(),
    )

    assert status_response.json()["napcat"]["running"] is False
    assert status_response.json()["napcat"]["webui"]["url"].endswith("/webui")
    assert start_response.json()["status"] == "not_configured"
    get_settings.cache_clear()


def test_qq_diagnostics_endpoint(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/diagnostics/qq")

    assert response.status_code == 200
    assert response.json()["api"]["running"] is True
    assert response.json()["api"]["onebot_url"].endswith("/onebot/v11/events")
    assert "napcat_webui" in response.json()
    assert "napcat_process" in response.json()
    assert "checks" in response.json()
    get_settings.cache_clear()


def test_telegram_diagnostics_endpoint(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/diagnostics/telegram")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "polling" in response.json()
    assert "checks" in response.json()
    get_settings.cache_clear()


def test_dashboard_onebot_diagnostic_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/diagnostics/onebot-test")

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_telegram_diagnostic_requires_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/dashboard-control/diagnostics/telegram-test")

    assert response.status_code == 401
    get_settings.cache_clear()


def test_dashboard_onebot_diagnostic_records_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/dashboard-control/diagnostics/onebot-test",
        headers=admin_headers(),
    )
    messages_response = client.get("/messages?conversation_id=qq:user:10001")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert messages_response.json()[0]["content"] == "ping"
    get_settings.cache_clear()


def test_dashboard_telegram_diagnostic_records_message(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/dashboard-control/diagnostics/telegram-test",
        headers=admin_headers(),
    )
    messages_response = client.get("/messages?conversation_id=telegram:user:10001")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert messages_response.json()[0]["content"] == "ping"
    get_settings.cache_clear()


def test_dashboard_telegram_getme_reports_missing_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/dashboard-control/diagnostics/telegram-getme",
        headers=admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"
    assert response.json()["ok"] is False
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
                "GUGABOBO_NAPCAT_DIR": "D:/tools/napcat",
                "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET": 0,
                "GUGABOBO_CLAUDE_BASE_URL": "https://gateway.example.com/",
                "GUGABOBO_GITHUB_REVIEW_ENABLED": True,
                "GUGABOBO_GITHUB_ORGANIZATION": "GugaBoBo-s",
                "GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS": 10,
                "GUGABOBO_GITHUB_ISSUE_ENABLED": True,
                "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED": True,
                "GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS": 10,
                "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN": 999,
                "GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE": 1.5,
                "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_REPOSITORIES": "GugaBoBo-s/gugabobo",
                "GUGABOBO_AUTO_DEPLOY_ENABLED": False,
                "GUGABOBO_CODE_CLAUDE_MODEL": "claude-code",
                "GUGABOBO_CODE_OPENAI_MODEL": "gpt-code",
                "GUGABOBO_CODE_DEEPSEEK_MODEL": "deepseek-code",
                "GUGABOBO_CODE_DEEPSEEK_RUNNER_MODEL": "deepseek-runner-code",
                "GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS": 0,
                "GUGABOBO_TELEGRAM_PROXY": "http://127.0.0.1:1080\nINJECTED=true",
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
    assert "GUGABOBO_NAPCAT_DIR=D:/tools/napcat" in env_text
    assert "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET=1" in env_text
    assert "GUGABOBO_CLAUDE_BASE_URL=https://gateway.example.com/" in env_text
    assert "GUGABOBO_GITHUB_REVIEW_ENABLED=true" in env_text
    assert "GUGABOBO_GITHUB_ORGANIZATION=GugaBoBo-s" in env_text
    assert "GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS=30" in env_text
    assert "GUGABOBO_GITHUB_ISSUE_ENABLED=true" in env_text
    assert "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED=true" in env_text
    assert "GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS=30" in env_text
    assert "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN=500" in env_text
    assert "GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE=1.0" in env_text
    assert "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_REPOSITORIES=GugaBoBo-s/gugabobo" in env_text
    assert "GUGABOBO_AUTO_DEPLOY_ENABLED=false" in env_text
    assert "GUGABOBO_CODE_CLAUDE_MODEL=claude-code" in env_text
    assert "GUGABOBO_CODE_OPENAI_MODEL=gpt-code" in env_text
    assert "GUGABOBO_CODE_DEEPSEEK_MODEL=deepseek-code" in env_text
    assert "GUGABOBO_CODE_DEEPSEEK_RUNNER_MODEL=deepseek-runner-code" in env_text
    assert "GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS=1" in env_text
    assert "INJECTED=true" in env_text
    assert "\nINJECTED=true\n" not in env_text
    assert "should-not-save" not in env_text
    assert "GUGABOBO_DEEPSEEK_API_KEY=secret" in env_text
    get_settings.cache_clear()


def test_code_review_scan_requires_admin_and_returns_result(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    class FakeCodeReviewService:
        def __init__(self, store):
            self.store = store

        def tick(self):
            return {
                "status": "ok",
                "enabled": True,
                "organization": "GugaBoBo-s",
                "repositories": 2,
                "pull_requests": 3,
                "reviewed": 2,
                "skipped": 1,
                "errors": 0,
            }

    monkeypatch.setattr(
        "gugabobo.api.server.OrganizationCodeReviewService",
        FakeCodeReviewService,
    )
    client = TestClient(app)

    unauthorized = client.post("/code-reviews/scan")
    response = client.post("/code-reviews/scan", headers=admin_headers())
    audits = client.get("/audit-logs").json()

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["reviewed"] == 2
    assert audits[0]["action"] == "code_review.scan"
    get_settings.cache_clear()


def test_github_issue_scan_requires_admin_and_returns_result(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)

    class FakeIssueService:
        def __init__(self, store):
            self.store = store

        def tick(self):
            return {
                "status": "ok",
                "enabled": True,
                "organization": "GugaBoBo-s",
                "repositories": 2,
                "issues": 4,
                "evaluated": 2,
                "worthwhile": 1,
                "pull_requests": 1,
                "skipped": 0,
                "errors": 0,
            }

    monkeypatch.setattr(
        "gugabobo.api.server.GitHubIssueAutomationService",
        FakeIssueService,
    )
    client = TestClient(app)

    unauthorized = client.post("/github-issues/scan")
    response = client.post("/github-issues/scan", headers=admin_headers())
    audits = client.get("/audit-logs").json()

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["pull_requests"] == 1
    assert audits[0]["action"] == "github_issue.scan"
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


def test_dashboard_control_writes_audit_logs(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/dashboard-control/memories",
        json={"subject": "global", "content": "审计测试"},
        headers=admin_headers(),
    )
    logs_response = client.get("/audit-logs")

    assert response.status_code == 200
    logs = logs_response.json()
    assert logs[0]["action"] == "memory.create"
    assert logs[0]["target"] == f"memory:{response.json()['id']}"
    assert logs[0]["risk_level"] == "normal"
    assert logs[0]["actor_source"] == "dashboard"
    assert logs[0]["actor_user_id"] == "admin"
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
    missing_confirmation_response = client.request(
        "DELETE",
        f"/dashboard-control/memories/{memory_id}",
        headers=admin_headers(),
    )
    delete_response = client.request(
        "DELETE",
        f"/dashboard-control/memories/{memory_id}",
        json={"confirm_text": "DELETE"},
        headers=admin_headers(),
    )
    after_delete_response = client.get("/memories?subject=telegram:user:1")
    audit_response = client.get("/audit-logs")

    assert update_response.status_code == 200
    assert filtered_response.json()[0]["content"] == "新内容"
    assert filtered_response.json()[0]["importance"] == 9
    assert missing_confirmation_response.status_code == 400
    assert delete_response.json()["deleted"] is True
    assert all(item["id"] != memory_id for item in after_delete_response.json())
    assert audit_response.json()[0]["action"] == "memory.delete"
    assert audit_response.json()[0]["risk_level"] == "high"
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

    clear_response = client.request(
        "DELETE",
        "/dashboard-control/conversations/dashboard:test/messages",
        json={"confirm_text": "CLEAR"},
        headers=admin_headers(),
    )
    messages_response = client.get("/messages?conversation_id=dashboard:test")
    delete_summary_response = client.request(
        "DELETE",
        "/dashboard-control/summaries/dashboard:test",
        json={"confirm_text": "DELETE"},
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
    delete_response = client.request(
        "DELETE",
        f"/dashboard-control/access-rules/{create_response.json()['id']}",
        json={"confirm_text": "DELETE"},
        headers=admin_headers(),
    )

    assert create_response.status_code == 200
    assert rules_response.json()[0]["role"] == "blocked"
    assert rules_response.json()[0]["notes"] == "spam"
    assert delete_response.json()["deleted"] is True
    get_settings.cache_clear()


class FakeGitHubClient:
    configured = True
    owner = "GugaBoBo-s"
    repo = "gugabobo"
    token = "token"

    def __init__(self, settings=None, owner=None, repo=None):
        self.owner = owner or "GugaBoBo-s"
        self.repo = repo or "gugabobo"

    def get_default_branch(self):
        return "main"

    def get_branch_sha(self, branch):
        return "sha"

    def try_get_branch_sha(self, branch):
        return ""

    def find_pull_request_by_head(self, branch):
        return {}

    def create_branch(self, branch, from_sha):
        return {}

    def put_file(self, path, content, message, branch):
        return {}

    def create_pull_request(self, title, head, base, body=""):
        from gugabobo.infra.github_client import PullRequestResult

        return PullRequestResult(number=11, url="https://github.com/x/y/pull/11", branch_name=head)

    def get_pull_request(self, number):
        return {"state": "closed", "merged": True, "merged_at": "2026-07-09T10:00:00Z",
                "head": {"sha": "abc"}}

    def get_checks_status(self, ref, required_name=""):
        return "success"


class FakeLifecycleGitHubClient(FakeGitHubClient):
    def get_pull_request(self, number):
        return {
            "state": "open",
            "merged": False,
            "merged_at": None,
            "merge_commit_sha": "",
            "head": {"sha": "abc"},
        }

    def merge_pull_request(self, number, commit_title, merge_method="squash", sha=""):
        from gugabobo.infra.github_client import MergeResult

        return MergeResult(merged=True, sha="merge-sha", message="merged")

    def close_pull_request(self, number):
        return {"state": "closed", "number": number}


def test_improvement_endpoints_require_admin_token(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/improvements", json={"feedback_id": 1})

    assert response.status_code == 401
    get_settings.cache_clear()


def test_improvement_create_approve_and_open_pr(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setattr("gugabobo.core.improvement.GitHubClient", FakeGitHubClient)
    client = TestClient(app)
    feedback_id = client.post("/feedbacks", json={"content": "回复太长"}).json()["id"]

    create_response = client.post(
        "/improvements",
        json={"feedback_id": feedback_id, "scope": "chat", "risk_level": "low"},
        headers=admin_headers(),
    )
    improvement_id = create_response.json()["improvement_id"]
    approve_response = client.post(
        f"/improvements/{improvement_id}/approve",
        json={"confirm_text": "APPROVE"},
        headers=admin_headers(),
    )
    missing_confirm = client.post(
        f"/improvements/{improvement_id}/pull-request",
        headers=admin_headers(),
    )
    pr_response = client.post(
        f"/improvements/{improvement_id}/pull-request",
        json={"confirm_text": "OPEN"},
        headers=admin_headers(),
    )
    prs_response = client.get("/prs")
    audit_response = client.get("/audit-logs")

    assert create_response.status_code == 200
    assert approve_response.json()["approval_status"] == "approved"
    assert missing_confirm.status_code == 400
    assert pr_response.status_code == 200
    assert pr_response.json()["number"] == 11
    assert prs_response.json()[0]["number"] == 11
    assert audit_response.json()[0]["action"] == "improvement.pr_open"
    assert audit_response.json()[0]["risk_level"] == "high"
    get_settings.cache_clear()


def test_sync_pull_request_endpoint(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setattr("gugabobo.core.improvement.GitHubClient", FakeGitHubClient)
    client = TestClient(app)
    feedback_id = client.post("/feedbacks", json={"content": "回复太长"}).json()["id"]
    improvement_id = client.post(
        "/improvements",
        json={"feedback_id": feedback_id},
        headers=admin_headers(),
    ).json()["improvement_id"]
    client.post(
        f"/improvements/{improvement_id}/approve",
        json={"confirm_text": "APPROVE"},
        headers=admin_headers(),
    )
    client.post(
        f"/improvements/{improvement_id}/pull-request",
        json={"confirm_text": "OPEN"},
        headers=admin_headers(),
    )
    pr_id = client.get("/prs").json()[0]["id"]

    unauth = client.post(f"/prs/{pr_id}/sync")
    sync_response = client.post(f"/prs/{pr_id}/sync", headers=admin_headers())

    assert unauth.status_code == 401
    assert sync_response.status_code == 200
    assert sync_response.json()["status"] == "merged"
    assert sync_response.json()["checks_status"] == "success"
    assert client.get(f"/prs/{pr_id}").json()["status"] == "merged"
    get_settings.cache_clear()


def test_dashboard_can_authorize_ci_gated_merge(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setenv("GUGABOBO_GITHUB_TOKEN", "token")
    get_settings.cache_clear()
    monkeypatch.setattr("gugabobo.core.improvement.GitHubClient", FakeGitHubClient)
    monkeypatch.setattr("gugabobo.core.lifecycle.GitHubClient", FakeLifecycleGitHubClient)
    client = TestClient(app)
    feedback_id = client.post("/feedbacks", json={"content": "回复太长"}).json()["id"]
    improvement_id = client.post(
        "/improvements",
        json={"feedback_id": feedback_id},
        headers=admin_headers(),
    ).json()["improvement_id"]
    client.post(
        f"/improvements/{improvement_id}/approve",
        json={"confirm_text": "APPROVE"},
        headers=admin_headers(),
    )
    client.post(
        f"/improvements/{improvement_id}/pull-request",
        json={"confirm_text": "OPEN"},
        headers=admin_headers(),
    )
    pr_id = client.get("/prs").json()[0]["id"]

    unauthenticated = client.post(
        f"/prs/{pr_id}/approve-merge",
        json={"confirm_text": "MERGE"},
    )
    missing_confirmation = client.post(
        f"/prs/{pr_id}/approve-merge",
        headers=admin_headers(),
    )
    approved = client.post(
        f"/prs/{pr_id}/approve-merge",
        json={"confirm_text": "MERGE"},
        headers=admin_headers(),
    )

    assert unauthenticated.status_code == 401
    assert missing_confirmation.status_code == 400
    assert approved.status_code == 200
    assert approved.json()["status"] == "merged"
    assert client.get("/merge-authorizations").json()[0]["status"] == "merged"
    assert client.get("/improvement-reflections").json()[0]["outcome"] == "merged"
    assert client.get("/deployments").json()[0]["target_revision"] == "merge-sha"
    get_settings.cache_clear()


def test_open_pr_before_approval_fails(tmp_path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    monkeypatch.setattr("gugabobo.core.improvement.GitHubClient", FakeGitHubClient)
    client = TestClient(app)
    feedback_id = client.post("/feedbacks", json={"content": "回复太长"}).json()["id"]
    improvement_id = client.post(
        "/improvements",
        json={"feedback_id": feedback_id},
        headers=admin_headers(),
    ).json()["improvement_id"]

    response = client.post(
        f"/improvements/{improvement_id}/pull-request",
        json={"confirm_text": "OPEN"},
        headers=admin_headers(),
    )

    assert response.status_code == 400
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
