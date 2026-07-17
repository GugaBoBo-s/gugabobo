from __future__ import annotations

import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx


_REQUEST_BLOCKED_HEADERS = {
    "authorization",
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "transfer-encoding",
    "x-api-key",
}
_RESPONSE_BLOCKED_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "transfer-encoding",
}


class _RelayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        upstream_base_url: str,
        upstream_token: str,
        relay_token: str,
        auth_mode: str,
        timeout: int,
    ) -> None:
        super().__init__(address, _RelayHandler)
        parsed = urlsplit(upstream_base_url.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("credential relay requires an HTTP upstream URL")
        self.upstream_scheme = parsed.scheme
        self.upstream_netloc = parsed.netloc
        self.upstream_path = parsed.path.rstrip("/")
        self.upstream_token = upstream_token
        self.relay_token = relay_token
        self.auth_mode = auth_mode
        self.timeout = timeout


class _RelayHandler(BaseHTTPRequestHandler):
    server: _RelayServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _forward(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        base = self.server.upstream_path
        if parsed.scheme or parsed.netloc or ".." in path.split("/"):
            self._respond(403, b"forbidden relay path")
            return
        if base and path != base and not path.startswith(f"{base}/"):
            self._respond(403, b"forbidden relay path")
            return
        authorization = self.headers.get("Authorization", "")
        api_key = self.headers.get("x-api-key", "")
        if (
            authorization != f"Bearer {self.server.relay_token}"
            and api_key != self.server.relay_token
        ):
            self._respond(401, b"invalid relay credential")
            return
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(content_length) if content_length else b""
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.casefold() not in _REQUEST_BLOCKED_HEADERS
        }
        if self.server.auth_mode == "api_key":
            headers["x-api-key"] = self.server.upstream_token
        else:
            headers["Authorization"] = f"Bearer {self.server.upstream_token}"
        upstream_url = urlunsplit(
            (
                self.server.upstream_scheme,
                self.server.upstream_netloc,
                parsed.path,
                parsed.query,
                "",
            )
        )
        try:
            with httpx.Client(timeout=self.server.timeout, follow_redirects=False) as client:
                response = client.request(self.command, upstream_url, headers=headers, content=body)
        except Exception:
            self._respond(502, b"upstream request failed")
            return
        response_body = response.content
        self.send_response(response.status_code)
        for name, value in response.headers.items():
            if name.casefold() not in _RESPONSE_BLOCKED_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CredentialRelay:
    def __init__(
        self,
        upstream_base_url: str,
        upstream_token: str,
        auth_mode: str = "bearer",
        timeout: int = 900,
    ) -> None:
        if auth_mode not in {"api_key", "bearer"}:
            raise ValueError("unsupported credential relay authentication mode")
        self.relay_token = secrets.token_urlsafe(32)
        self._server = _RelayServer(
            ("0.0.0.0", 0),
            upstream_base_url,
            upstream_token,
            self.relay_token,
            auth_mode,
            timeout,
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def container_base_url(self) -> str:
        port = int(self._server.server_address[1])
        return f"http://host.docker.internal:{port}{self._server.upstream_path}"

    @property
    def local_base_url(self) -> str:
        port = int(self._server.server_address[1])
        return f"http://127.0.0.1:{port}{self._server.upstream_path}"

    def __enter__(self) -> CredentialRelay:
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._server.upstream_token = ""
        self._server.relay_token = ""
        self._thread.join(timeout=5)
