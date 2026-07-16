import httpx
import pytest

from gugabobo.config import get_settings
from gugabobo.infra.github_client import GitHubClient


def configure_token(monkeypatch, token: str = "ghp_test") -> None:
    monkeypatch.setenv("GUGABOBO_GITHUB_TOKEN", token)
    monkeypatch.setenv("GUGABOBO_GITHUB_OWNER", "GugaBoBo-s")
    monkeypatch.setenv("GUGABOBO_GITHUB_REPO", "gugabobo")
    monkeypatch.setenv("GUGABOBO_GITHUB_API_URL", "https://api.github.com")
    get_settings.cache_clear()


def install_mock(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def capturing(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(capturing)
    original_client = httpx.Client

    def build_client(**kwargs):
        kwargs.pop("transport", None)
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", build_client)
    return seen


def test_client_reports_unconfigured(monkeypatch):
    monkeypatch.setenv("GUGABOBO_GITHUB_TOKEN", "")
    get_settings.cache_clear()

    client = GitHubClient()

    assert client.configured is False
    with pytest.raises(RuntimeError):
        client.get_default_branch()
    get_settings.cache_clear()


def test_create_pull_request_flow(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls") and request.method == "POST":
            return httpx.Response(
                201,
                json={"number": 42, "html_url": "https://github.com/GugaBoBo-s/gugabobo/pull/42"},
            )
        return httpx.Response(404, json={})

    seen = install_mock(monkeypatch, handler)
    client = GitHubClient()

    result = client.create_pull_request(title="t", head="gugabobo/x", base="main", body="b")

    assert result.number == 42
    assert result.url.endswith("/pull/42")
    request = seen[0]
    assert request.headers["Authorization"] == "Bearer ghp_test"
    assert request.url.path == "/repos/GugaBoBo-s/gugabobo/pulls"
    get_settings.cache_clear()


def test_put_file_encodes_content(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"commit": {"sha": "abc"}})

    seen = install_mock(monkeypatch, handler)
    client = GitHubClient()

    client.put_file(path="improvements/1.md", content="hello", message="m", branch="b")

    import base64
    import json

    body = json.loads(seen[0].content)
    assert base64.b64decode(body["content"]).decode("utf-8") == "hello"
    assert body["branch"] == "b"
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], "unknown"),
        ([{"status": "in_progress", "conclusion": None}], "pending"),
        ([{"status": "completed", "conclusion": "success"}], "success"),
        ([{"status": "completed", "conclusion": "failure"}], "failure"),
    ],
)
def test_check_run_status_is_aggregated(monkeypatch, runs, expected):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/commits/abc/check-runs")
        return httpx.Response(200, json={"check_runs": runs})

    install_mock(monkeypatch, handler)

    assert GitHubClient().get_checks_status("abc") == expected
    get_settings.cache_clear()


def test_check_run_permission_denied_is_unknown(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/commits/abc/check-runs")
        return httpx.Response(403, json={"message": "Resource not accessible by token"})

    install_mock(monkeypatch, handler)

    assert GitHubClient().get_checks_status("abc") == "unknown"
    get_settings.cache_clear()


def test_push_url_does_not_embed_token(monkeypatch):
    configure_token(monkeypatch, token="ghp_secret_value")

    url = GitHubClient().push_url

    assert "ghp_secret_value" not in url
    assert url == "https://x-access-token@github.com/GugaBoBo-s/gugabobo.git"
    get_settings.cache_clear()
