from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from gugabobo.infra.logs import get_logger


class McpError(RuntimeError):
    """Raised when an MCP endpoint returns a JSON-RPC error or malformed reply."""


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: dict[str, object] = field(default_factory=dict)


class McpClient:
    """Minimal MCP client over the Streamable HTTP transport.

    Talks to a single endpoint with JSON-RPC 2.0 requests, carrying a Bearer
    token. Responses may arrive as plain JSON or as a one-shot text/event-stream
    frame; both are handled. A session id returned on initialize is echoed on
    later requests for servers that keep state.
    """

    def __init__(
        self,
        url: str,
        token: str = "",
        timeout: float = 30.0,
        proxy: str | None = None,
        protocol_version: str = "2025-06-18",
        client_name: str = "gugabobo",
    ) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.proxy = proxy
        self.protocol_version = protocol_version
        self.client_name = client_name
        self._session_id: str | None = None
        self._request_id = 0

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, proxy=self.proxy) as client:
            return client.post(self.url, headers=self._headers(), json=payload)

    def _request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        response = self._post(payload)
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        if response.status_code >= 400:
            raise McpError(f"HTTP {response.status_code}: {response.text[:200]}")
        message = _parse_response_body(response)
        if "error" in message:
            error = message["error"]
            if isinstance(error, dict):
                raise McpError(str(error.get("message") or error))
            raise McpError(str(error))
        result = message.get("result")
        if not isinstance(result, dict):
            raise McpError("MCP response missing result object")
        return result

    def _notify(self, method: str) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": {}}
        try:
            self._post(payload)
        except httpx.HTTPError as exc:
            get_logger().debug("MCP notification %s failed: %s", method, exc)

    def initialize(self) -> dict[str, object]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": "0.1"},
            },
        )
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> list[McpTool]:
        result = self._request("tools/list", {})
        tools: list[McpTool] = []
        for entry in result.get("tools", []):
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            schema = entry.get("inputSchema")
            tools.append(
                McpTool(
                    name=name,
                    description=str(entry.get("description", "")).strip(),
                    input_schema=schema if isinstance(schema, dict) else {},
                )
            )
        return tools

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        return self._request("tools/call", {"name": name, "arguments": arguments})


def _parse_response_body(response: httpx.Response) -> dict[str, object]:
    content_type = response.headers.get("content-type", "")
    text = response.text.strip()
    if "text/event-stream" in content_type:
        message = _parse_sse(text)
        if message is None:
            raise McpError("MCP SSE response contained no data frame")
        return message
    try:
        message = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise McpError(f"invalid MCP JSON response: {text[:200]}") from exc
    if not isinstance(message, dict):
        raise McpError("MCP response was not a JSON object")
    return message


def _parse_sse(text: str) -> dict[str, object] | None:
    """Extract the last JSON-RPC message from a text/event-stream body."""

    last: dict[str, object] | None = None
    data_lines: list[str] = []
    for raw_line in text.splitlines() + [""]:
        line = raw_line.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
            continue
        if line == "" and data_lines:
            payload = "\n".join(data_lines)
            data_lines = []
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                last = parsed
    return last


def tool_result_to_text(result: dict[str, object]) -> str:
    """Render an MCP tools/call result into plain text for the LLM."""

    parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
    if not parts:
        structured = result.get("structuredContent")
        if structured is not None:
            parts.append(json.dumps(structured, ensure_ascii=False))
    rendered = "\n".join(parts) if parts else "（工具无返回内容）"
    if result.get("isError"):
        return f"工具返回错误：{rendered}"
    return rendered
