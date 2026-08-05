"""Combined MCP server exposing every taskflow tool (tasks, workflows, notes,
reminders, calendar) through a single remote MCP endpoint (streamable-http),
for connectors that need one server URL rather than N local stdio processes
-- e.g. ChatGPT's Connectors UI, which can't spawn a local subprocess the
way Claude Desktop's per-connector stdio config does.

This doesn't reimplement anything: it imports the five existing stdio
servers (mcp_tasks_server.py etc.) and re-registers each of their already-
defined tools onto one new MCPServer instance, so this file and those stay
in sync automatically -- add a tool to mcp_notes_server.py and it shows up
here too, no duplication.

Tool names are prefixed by area (tasks_, workflow_, notes_, reminders_,
calendar_) because a couple of names collide across the underlying modules
(e.g. both mcp_tasks_server and mcp_workflow_server define update_task, for
different kinds of tasks) -- the individual servers rely on being separate
MCP servers for that disambiguation; combined into one flat tool namespace,
the prefix is what keeps them distinct instead.

Run directly (binds to all interfaces so a tunnel can reach it):
    python mcp_combined_server.py
Override host/port/path with env vars: MCP_HTTP_HOST, MCP_HTTP_PORT,
MCP_HTTP_PATH (defaults: 0.0.0.0, 8420, /mcp).

SECURITY: this has no authentication of its own -- anyone who can reach the
URL can call every tool below, including ones that create/edit/delete real
data. If exposing it beyond localhost (a tunnel, a public host), put auth in
front of it (e.g. `cloudflared tunnel --url ... ` has no built-in auth either;
`ngrok http --basic-auth "user:pass" <port>` does, or use Cloudflare Access).
"""

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import mcp_tasks_server as _tasks
import mcp_workflow_server as _workflows
import mcp_notes_server as _notes
import mcp_reminders_server as _reminders
import mcp_calendar_server as _calendar

server = MCPServer(
    name="taskflow",
    instructions=(
        "Combined tools for the user's taskflow app -- standalone Tasks, "
        "Workflows (steps + action-item tasks), Notes (Books > Chapters > "
        "Pages), standalone Reminders, and Meetings/Calendar. Tool names "
        "are prefixed by area: tasks_*, workflow_*, notes_*, reminders_*, "
        "calendar_*. Each prefix's tools carry the same usage notes as the "
        "original per-area server they came from (valid status/priority/"
        "recurrence values, plain-text vs HTML fields, etc.) -- read each "
        "tool's own description before calling it."
    ),
)

_SOURCES = [
    ("tasks", _tasks.server),
    ("workflow", _workflows.server),
    ("notes", _notes.server),
    ("reminders", _reminders.server),
    ("calendar", _calendar.server),
]

for _prefix, _sub_server in _SOURCES:
    for _tool in _sub_server._tool_manager._tools.values():
        server.add_tool(
            _tool.fn,
            name=f"{_prefix}_{_tool.name}",
            title=_tool.title,
            description=_tool.description,
            annotations=_tool.annotations,
            icons=_tool.icons,
            meta=_tool.meta,
        )


if __name__ == "__main__":
    host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_HTTP_PORT", "8420"))
    path = os.environ.get("MCP_HTTP_PATH", "/mcp")

    # The SDK's DNS-rebinding protection rejects any request whose Host header
    # isn't in an explicit allowlist -- meant to stop a malicious webpage from
    # tricking a browser into hitting a server that only *meant* to be
    # localhost-only. That doesn't apply here: this server is deliberately
    # exposed (via a tunnel with a hostname that changes every run), so there's
    # no fixed host to allowlist and no accidental-exposure scenario to guard
    # against. Disabling it is what makes running this behind a tunnel work at
    # all -- ChatGPT's requests arrive with the tunnel's own Host header.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    server.run(transport="streamable-http", host=host, port=port,
               streamable_http_path=path, transport_security=security)
