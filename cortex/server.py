from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cortex", instructions="Cortex — persistent context brain for Claude Code sessions. All tools migrated to CLI. Use `cortex` command via Bash. See /cortex-cli skill for reference.")

# MCP tools removed — all functionality available via cortex CLI.
# Server kept running for MCP Channels support (CC 2.1.80+).
# See plugin/skills/cortex-cli/MIGRATION.md for before/after mapping.


def main() -> None:
    from cortex.observability import setup_logging

    setup_logging("mcp")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
