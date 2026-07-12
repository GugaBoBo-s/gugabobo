from gugabobo.infra import images
from gugabobo.infra.images import _detect_mime, urls_to_data_uris


def test_detect_mime_png():
    assert _detect_mime(b"\x89PNG\r\n\x1a\n rest") == "image/png"


def test_detect_mime_jpeg():
    assert _detect_mime(b"\xff\xd8\xff\xe0 rest") == "image/jpeg"


def test_detect_mime_defaults_to_jpeg():
    assert _detect_mime(b"unknown-bytes") == "image/jpeg"


def test_url_to_data_uri_returns_data_uri(monkeypatch):
    class FakeResponse:
        content = b"\x89PNG\r\n\x1a\nfoo"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(images.httpx, "Client", FakeClient)

    data_uri = images.url_to_data_uri("https://example.com/a.png")

    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")


def test_url_to_data_uri_returns_none_on_error(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise RuntimeError("network down")

    monkeypatch.setattr(images.httpx, "Client", FakeClient)

    assert images.url_to_data_uri("https://example.com/a.png") is None


def test_urls_to_data_uris_skips_failed(monkeypatch):
    results = iter(["data:image/png;base64,AAAA", None])
    monkeypatch.setattr(images, "url_to_data_uri", lambda url, timeout=20.0: next(results))

    assert urls_to_data_uris(["u1", "u2"]) == ["data:image/png;base64,AAAA"]
