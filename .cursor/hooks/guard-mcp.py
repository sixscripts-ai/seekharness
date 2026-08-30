#!/usr/bin/env python3
"""beforeMCPExecution backup gate. Does not make tools read-only; it only allow/ask/deny."""

from __future__ import annotations

import json
import sys

# Production-capable Vercel tools (capability gate; mcpAllowlist is auto-approval only).
_VERCEL_DENY = {
    "buy_domain",
    "buy_addon",
    "buy_credits",
    "buy_pro",
    "get_purchase_quote",
}

_VERCEL_SERVERS = {"plugin-vercel-vercel", "vercel"}
_FILESYSTEM_WRITE = {"write_file", "edit_file", "move_file", "create_directory"}
_FILESYSTEM_SERVERS = {"user-filesystem", "filesystem"}


def _emit(permission: str, user_message: str = "", agent_message: str = "") -> None:
    payload: dict[str, str] = {"permission": permission}
    if user_message:
        payload["user_message"] = user_message
    if agent_message:
        payload["agent_message"] = agent_message
    sys.stdout.write(json.dumps(payload))
    sys.exit(0)


def classify(server: str, tool: str) -> tuple[str, str, str]:
    server_l = server.lower()
    tool_l = tool.lower()
    if server_l in _VERCEL_SERVERS and tool_l in _VERCEL_DENY:
        return (
            "deny",
            "Vercel billing/domain purchase tools stay blocked.",
            f"Hook denied Vercel tool {tool}.",
        )
    if server_l in _FILESYSTEM_SERVERS and tool_l in _FILESYSTEM_WRITE:
        return (
            "deny",
            "Filesystem MCP writes to ~/Documents are blocked in Agent Arena.",
            f"Hook denied filesystem write tool {tool}.",
        )
    return "allow", "", ""


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        server = str(data.get("mcp_server_name") or "")
        tool = str(data.get("tool_name") or "")
        permission, user_message, agent_message = classify(server, tool)
        _emit(permission, user_message, agent_message)
    except Exception as exc:
        _emit("deny", "MCP guard failed closed.", f"Hook error: {exc}")


if __name__ == "__main__":
    main()
