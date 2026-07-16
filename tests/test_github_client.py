import json

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


def test_merge_and_close_pull_request(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.endswith("/pulls/15/merge"):
            return httpx.Response(200, json={"merged": True, "sha": "abc", "message": "ok"})
        if request.method == "PATCH" and request.url.path.endswith("/pulls/15"):
            return httpx.Response(200, json={"number": 15, "state": "closed"})
        return httpx.Response(404, json={})

    seen = install_mock(monkeypatch, handler)
    client = GitHubClient()

    merged = client.merge_pull_request(15, "Merge PR #15", sha="head-sha")
    closed = client.close_pull_request(15)

    assert merged.merged is True
    assert merged.sha == "abc"
    assert json.loads(seen[0].content)["sha"] == "head-sha"
    assert closed["state"] == "closed"
    assert [request.method for request in seen] == ["PUT", "PATCH"]
    get_settings.cache_clear()


def test_authenticated_login_and_pull_request_recovery(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "gugabobo-agent"})
        if request.url.path.endswith("/pulls"):
            assert request.url.params["head"] == "GugaBoBo-s:gugabobo/improvement-7"
            assert request.url.params["state"] == "all"
            return httpx.Response(200, json=[{"number": 17, "html_url": "https://example/pr/17"}])
        if request.url.path.endswith("/git/ref/heads/missing"):
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404, json={})

    install_mock(monkeypatch, handler)
    client = GitHubClient()

    assert client.get_authenticated_login() == "gugabobo-agent"
    assert client.find_pull_request_by_head("gugabobo/improvement-7")["number"] == 17
    assert client.try_get_branch_sha("missing") == ""
    get_settings.cache_clear()


def test_organization_pull_request_and_file_listing_are_paginated(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        if request.url.path == "/orgs/GugaBoBo-s/repos":
            items = [{"name": f"repo-{index}"} for index in range(100)] if page == 1 else []
            if page == 2:
                items = [{"name": "repo-100"}]
            return httpx.Response(200, json=items)
        if request.url.path.endswith("/pulls"):
            items = [{"number": index} for index in range(100)] if page == 1 else []
            if page == 2:
                items = [{"number": 100}]
            return httpx.Response(200, json=items)
        if request.url.path.endswith("/pulls/7/files"):
            return httpx.Response(200, json=[{"filename": "a.py"}, {"filename": "b.py"}])
        return httpx.Response(404, json={})

    seen = install_mock(monkeypatch, handler)
    client = GitHubClient()

    repositories = client.list_organization_repositories("GugaBoBo-s")
    pull_requests = client.list_pull_requests()
    files = client.list_pull_request_files(7, limit=1)

    assert len(repositories) == 101
    assert repositories[-1] == {"name": "repo-100"}
    assert len(pull_requests) == 101
    assert pull_requests[-1] == {"number": 100}
    assert files == [{"filename": "a.py"}]
    assert all(request.url.params["per_page"] == "100" for request in seen)
    get_settings.cache_clear()


def test_create_pull_request_review_uses_comment_event(monkeypatch):
    configure_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": 9, "html_url": "https://github.com/GugaBoBo-s/gugabobo/pull/7#review-9"},
        )

    seen = install_mock(monkeypatch, handler)

    result = GitHubClient().create_pull_request_review(7, "review body", "head-sha")
    payload = json.loads(seen[0].content)

    assert result.review_id == 9
    assert seen[0].url.path.endswith("/pulls/7/reviews")
    assert payload == {"body": "review body", "commit_id": "head-sha", "event": "COMMENT"}
    get_settings.cache_clear()
