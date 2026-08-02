"""MCP server exposing this app's Meetings (the closest thing it has to a
calendar: dated/timed events with an optional agenda of discussion points) to
Claude Desktop as a custom connector.

This is a thin client over the existing Flask HTTP API (task_manager.py's
/meetings and /meeting-points routes) -- it does not touch the database
directly, so it can never drift from the app's own validation/recurrence
logic, and it requires the taskflow app to be running (default
http://localhost:5001, override with the TASKFLOW_API_URL env var).

This is TaskFlow's own local calendar, not an external one -- it has no
connection to Google Calendar, Outlook, or any other outside service.
"""

import os
import requests

from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("TASKFLOW_API_URL", "http://localhost:5001").rstrip("/")
TIMEOUT = 10

STATUSES = ["upcoming", "completed", "cancelled"]
RECURRENCES = ["none", "daily", "weekdays", "weekly", "biweekly", "monthly"]

server = MCPServer(
    name="taskflow-calendar",
    instructions=(
        "Tools for reading and managing the user's Meetings (TaskFlow's own "
        "local calendar -- NOT connected to Google Calendar/Outlook/etc) in "
        "their taskflow app. Each meeting has a date/time/location and an "
        "optional ordered list of agenda discussion points, each of which can "
        "be checked off. "
        f"Valid meeting statuses: {', '.join(STATUSES)}. Valid recurrence "
        f"values: {', '.join(RECURRENCES)} -- completing a recurring meeting "
        "auto-spawns the next occurrence, so don't create it yourself. "
        "date is 'YYYY-MM-DD', time is 'HH:MM' (24h), duration_minutes is an "
        "integer. Use list_meetings to find a meeting's id, then get_meeting "
        "for its full agenda. Title/description/agenda text is plain text, "
        "not HTML -- pass raw characters like '&' directly, never "
        "HTML-entity-encode them."
    ),
)


def _request(method, path, **kwargs):
    try:
        r = requests.request(method, f"{API_BASE}{path}", timeout=TIMEOUT, **kwargs)
    except requests.exceptions.ConnectionError:
        return None, f"Could not reach the taskflow app at {API_BASE}. Is it running?"
    except requests.exceptions.Timeout:
        return None, f"Request to the taskflow app timed out ({API_BASE}{path})."
    if not r.ok:
        try:
            detail = r.json().get("error", r.text)
        except ValueError:
            detail = r.text
        return None, f"taskflow app returned {r.status_code}: {detail}"
    return (r.json() if r.content else {}), None


def _slim(m):
    return {
        "id": m["id"], "title": m["title"], "date": m["date"], "time": m.get("time"),
        "duration_minutes": m.get("duration_minutes"), "location": m.get("location") or "",
        "status": m["status"], "recurrence": m.get("recurrence"),
        "points_done": m.get("point_done", 0), "points_total": m.get("point_total", 0),
    }


@server.tool()
def list_meetings(upcoming_only: bool = False) -> dict:
    """List meetings ordered by date/time. Set upcoming_only=True to exclude
    completed/cancelled ones."""
    data, err = _request("GET", "/meetings")
    if err:
        return {"error": err}
    if upcoming_only:
        data = [m for m in data if m["status"] not in ("completed", "cancelled")]
    return {"meetings": [_slim(m) for m in data]}


@server.tool()
def get_meeting(meeting_id: int) -> dict:
    """Get one meeting's full detail: all fields plus its complete ordered
    agenda (every discussion point, done or not)."""
    data, err = _request("GET", "/meetings")
    if err:
        return {"error": err}
    m = next((m for m in data if m["id"] == meeting_id), None)
    if not m:
        return {"error": f"No meeting with id {meeting_id}."}
    points, err = _request("GET", f"/meetings/{meeting_id}/points")
    if err:
        return {"error": err}
    out = _slim(m)
    out["description"] = m.get("description") or ""
    out["agenda"] = [{"id": p["id"], "content": p["content"], "is_done": bool(p["is_done"])} for p in points]
    return out


@server.tool()
def create_meeting(title: str, date: str, time: str = None, duration_minutes: int = 60,
                    location: str = "", description: str = "", recurrence: str = "none") -> dict:
    """Schedule a new meeting."""
    if recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    data, err = _request("POST", "/meetings", json={
        "title": title, "date": date, "time": time, "duration_minutes": duration_minutes,
        "location": location, "description": description, "recurrence": recurrence,
    })
    return {"error": err} if err else _slim(data)


@server.tool()
def update_meeting(meeting_id: int, title: str = None, date: str = None, time: str = None,
                    duration_minutes: int = None, location: str = None, description: str = None,
                    status: str = None, recurrence: str = None) -> dict:
    """Update a meeting. Only the fields you pass are changed."""
    if status is not None and status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {', '.join(STATUSES)}"}
    if recurrence is not None and recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    payload = {k: v for k, v in {
        "title": title, "date": date, "time": time, "duration_minutes": duration_minutes,
        "location": location, "description": description, "status": status, "recurrence": recurrence,
    }.items() if v is not None}
    if not payload:
        return {"error": "Nothing to update -- pass at least one field."}
    data, err = _request("PUT", f"/meetings/{meeting_id}", json=payload)
    return {"error": err} if err else _slim(data)


@server.tool()
def delete_meeting(meeting_id: int) -> dict:
    """Permanently delete a meeting and its agenda."""
    data, err = _request("DELETE", f"/meetings/{meeting_id}")
    return {"error": err} if err else data


@server.tool()
def add_agenda_point(meeting_id: int, content: str) -> dict:
    """Add a new discussion point to the end of a meeting's agenda."""
    data, err = _request("POST", f"/meetings/{meeting_id}/points", json={"content": content})
    return {"error": err} if err else data


@server.tool()
def update_agenda_point(point_id: int, content: str = None, is_done: bool = None) -> dict:
    """Edit and/or check off a single agenda point. Only the fields you pass
    are changed."""
    payload = {}
    if content is not None:
        payload["content"] = content
    if is_done is not None:
        payload["is_done"] = is_done
    if not payload:
        return {"error": "Nothing to update -- pass content and/or is_done."}
    data, err = _request("PUT", f"/meeting-points/{point_id}", json=payload)
    return {"error": err} if err else data


if __name__ == "__main__":
    # Claude Desktop's Settings > Developer > "Local MCP servers" launches this
    # script itself as a subprocess and talks to it over stdio.
    server.run(transport="stdio")
