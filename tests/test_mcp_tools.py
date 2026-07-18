from __future__ import annotations

from gugabobo.core.tools import ToolContext, ToolRegistry, build_mcp_tools
from gugabobo.infra.mcp_client import McpTool
from gugabobo.memory.store import MemoryStore


class FakeMcpClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return [
            McpTool(
                name="query-meals",
                description="查询门店餐品",
                input_schema={"type": "object", "properties": {"storeId": {"type": "string"}}},
            ),
            McpTool(name="create-order", description="创建订单", input_schema={}),
        ]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": f"ok:{name}"}]}


def _registry_with_mcd():
    registry = ToolRegistry()
    tools = build_mcp_tools(FakeMcpClient(), prefix="mcd", min_skill="owner_action")
    registry.register(tools)
    return registry


def test_build_mcp_tools_prefixes_names_and_keeps_schema():
    tools = build_mcp_tools(FakeMcpClient(), prefix="mcd")
    names = {t.name for t in tools}
    assert names == {"mcd_query-meals", "mcd_create-order"}
    meals = next(t for t in tools if t.name == "mcd_query-meals")
    assert meals.parameters["properties"]["storeId"]["type"] == "string"
    assert meals.min_skill == "owner_action"


def test_owner_can_dispatch_mcd_tool(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    registry = _registry_with_mcd()
    ctx = ToolContext(
        store=store,
        conversation_id="person:1:direct",
        access_role="owner",
        source="qq_private",
        user_id="1",
    )

    out = registry.dispatch("mcd_query-meals", '{"storeId": "42"}', ctx)

    assert out == "ok:query-meals"
    logs = store.list_audit_logs(limit=5)
    assert any(log["action"] == "tool.mcp.mcd.query-meals" for log in logs)


def test_non_owner_cannot_dispatch_mcd_tool(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    registry = _registry_with_mcd()
    ctx = ToolContext(store=store, conversation_id="c", access_role="user")

    out = registry.dispatch("mcd_create-order", "{}", ctx)

    assert "权限" in out


def test_mcd_tools_hidden_from_user_specs(tmp_path):
    registry = _registry_with_mcd()
    user_names = {spec["function"]["name"] for spec in registry.specs_for("user")}
    owner_names = {spec["function"]["name"] for spec in registry.specs_for("owner")}
    assert "mcd_query-meals" not in user_names
    assert "mcd_query-meals" in owner_names
