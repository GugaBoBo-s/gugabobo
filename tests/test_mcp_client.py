from __future__ import annotations

import httpx
import pytest

from gugabobo.infra.mcp_client import (
    McpClient,
    McpError,
    _parse_sse,
    tool_result_to_text,
)


def _make_client(handler) -> McpClient:
    transport = httpx.MockTransport(handler)
    client = McpClient(url="https://mcp.example/", token="secret", timeout=5)

    def _post(payload):
        with httpx.Client(transport=transport, timeout=5) as http:
            return http.post(client.url, headers=client._headers(), json=payload)

    client._post = _post  # type: ignore[assignment]
    return client


def test_parse_sse_extracts_last_json_frame():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    parsed = _parse_sse(body)
    assert parsed == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_parse_sse_multiline_data():
    body = 'data: {"jsonrpc":"2.0",\ndata: "id":2,"result":{"v":1}}\n\n'
    parsed = _parse_sse(body)
    assert parsed == {"jsonrpc": "2.0", "id": 2, "result": {"v": 1}}


def test_initialize_and_headers_carry_token():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        body = request.content.decode()
        if "initialize" in body:
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "x"}}},
                headers={"mcp-session-id": "sess-1"},
            )
        return httpx.Response(202)

    client = _make_client(handler)
    result = client.initialize()

    assert result["serverInfo"]["name"] == "x"
    assert seen["auth"] == "Bearer secret"
    assert client._session_id == "sess-1"


def test_list_tools_parses_schema():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {
                            "name": "query-meals",
                            "description": "查询餐品",
                            "inputSchema": {"type": "object", "properties": {"storeId": {"type": "string"}}},
                        },
                        {"name": "", "description": "skip me"},
                    ]
                },
            },
        )

    client = _make_client(handler)
    tools = client.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "query-meals"
    assert tools[0].input_schema["properties"]["storeId"]["type"] == "string"


def test_call_tool_reads_sse_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content='data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"巨无霸"}]}}\n\n',
        )

    client = _make_client(handler)
    result = client.call_tool("query-meals", {"storeId": "1"})

    assert tool_result_to_text(result) == "巨无霸"


def test_request_raises_on_jsonrpc_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "无效 token"}},
        )

    client = _make_client(handler)
    with pytest.raises(McpError, match="无效 token"):
        client.list_tools()


def test_request_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = _make_client(handler)
    with pytest.raises(McpError, match="401"):
        client.list_tools()


def test_tool_result_to_text_flags_errors():
    result = {"isError": True, "content": [{"type": "text", "text": "库存不足"}]}
    assert "错误" in tool_result_to_text(result)


def test_tool_result_to_text_falls_back_to_structured():
    result = {"structuredContent": {"points": 100}}
    assert "100" in tool_result_to_text(result)
