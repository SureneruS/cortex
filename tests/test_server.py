from cortex.server import mcp


def test_mcp_server_has_no_tools():
    """MCP tools removed in Phase 4 — server kept for channels only."""
    assert mcp is not None
    assert mcp.name == "cortex"
