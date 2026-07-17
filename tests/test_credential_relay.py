from urllib.error import HTTPError
from urllib.request import Request, urlopen

from httpx import Response

from gugabobo.infra import credential_relay as relay_module
from gugabobo.infra.credential_relay import CredentialRelay


class FakeHttpClient:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def request(self, method, url, headers, content):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "content": content,
            }
        )
        return Response(200, content=b'{"ok":true}', headers={"Content-Type": "application/json"})


def test_relay_replaces_short_lived_credential_with_upstream_secret(monkeypatch) -> None:
    FakeHttpClient.calls = []
    monkeypatch.setattr(relay_module.httpx, "Client", FakeHttpClient)

    with CredentialRelay(
        "https://gateway.example.com/v1",
        "upstream-secret",
        auth_mode="bearer",
    ) as relay:
        request = Request(
            f"{relay.local_base_url}/responses",
            data=b"{}",
            headers={"Authorization": f"Bearer {relay.relay_token}"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            assert response.read() == b'{"ok":true}'

    call = FakeHttpClient.calls[0]
    assert call["url"] == "https://gateway.example.com/v1/responses"
    assert call["headers"]["Authorization"] == "Bearer upstream-secret"
    assert relay.relay_token not in str(call)


def test_relay_rejects_requests_without_ephemeral_credential(monkeypatch) -> None:
    FakeHttpClient.calls = []
    monkeypatch.setattr(relay_module.httpx, "Client", FakeHttpClient)

    with CredentialRelay("https://gateway.example.com/v1", "upstream-secret") as relay:
        request = Request(
            f"{relay.local_base_url}/responses",
            data=b"{}",
            method="POST",
        )
        try:
            urlopen(request, timeout=5)
        except HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("relay accepted an unauthenticated request")

    assert FakeHttpClient.calls == []
