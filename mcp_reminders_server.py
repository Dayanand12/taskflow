"""MCP server exposing this app's Reminders -- both reminders attached to a
Task and standalone Reminders (not tied to any task) -- to Claude Desktop as
a custom connector.

This is a thin client over the existing Flask HTTP API (task_manager.py's
/reminders and /standalone-reminders routes) -- it does not touch the
database directly, so it can never drift from the app's own
validation/recurrence logic, and it requires the taskflow app to be running
(default http://localhost:5001, override with the TASKFLOW_API_URL env var).

A task can have at most one active reminder (setting a new one deactivates
the old one, matching the app's own behavior). Standalone reminders are
independent, freestanding alerts (e.g. "call the vet", "pay rent") and are
the only kind with their own title/note/type.
"""

import os
import requests

from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("TASKFLOW_API_URL", "http://localhost:5001").rstrip("/")
TIMEOUT = 10

RECURRENCES = ["none", "daily", "weekdays", "weekly", "monthly"]
REMINDER_TYPES = ["meeting", "call", "task", "deadline", "personal", "general"]

server = MCPServer(
    name="taskflow-reminders",
    instructions=(
        "Tools for reading and managing the user's Reminders in their local "
        "taskflow app: reminders attached to an existing Task, and freestanding "
        "standalone reminders. "
        "remind_at is a local datetime string 'YYYY-MM-DD HH:MM' (24h clock). "
        f"Valid recurrence values for a reminder: {', '.join(RECURRENCES)}. "
        f"Valid standalone reminder_type values: {', '.join(REMINDER_TYPES)} "
        "(purely cosmetic icon/grouping, pick whichever fits best). "
        "Use list_reminders to see everything active, or get_due_reminders for "
        "just what's due right now. Title/note text is plain text, not HTML -- "
        "pass raw characters like '&' directly, never HTML-entity-encode them."
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


@server.tool()
def list_reminders() -> dict:
    """List every active reminder, both task-attached and standalone, each
    tagged with its kind ('task' or 'standalone')."""
    task_data, err = _request("GET", "/reminders")
    if err:
        return {"error": err}
    standalone_data, err = _request("GET", "/standalone-reminders")
    if err:
        return {"error": err}

    tasks_by_id = {}
    if task_data:
        all_tasks, err = _request("GET", "/tasks")
        if err:
            return {"error": err}
        tasks_by_id = {t["id"]: t["title"] for t in all_tasks}

    out = []
    for r in task_data:
        out.append({
            "kind": "task", "reminder_id": r["id"], "task_id": r["task_id"],
            "task_title": tasks_by_id.get(r["task_id"], f"#{r['task_id']}"),
            "remind_at": r["remind_at"], "recurrence": r["recurrence"],
        })
    for r in standalone_data:
        out.append({
            "kind": "standalone", "reminder_id": r["id"], "title": r["title"],
            "note": r.get("note") or "", "reminder_type": r["reminder_type"],
            "remind_at": r["remind_at"], "recurrence": r["recurrence"],
        })
    out.sort(key=lambda r: r["remind_at"])
    return {"reminders": out}


@server.tool()
def get_due_reminders() -> dict:
    """List reminders (task-attached and standalone) that are due right now --
    i.e. their remind_at has passed and they haven't been snoozed past now."""
    data, err = _request("GET", "/reminders/due")
    if err:
        return {"error": err}
    return {
        "due": [
            {
                "kind": r["rem_type"], "reminder_id": r["id"],
                "title": r.get("task_title") or r.get("title"),
                "remind_at": r["remind_at"], "recurrence": r["recurrence"],
            }
            for r in data
        ]
    }


@server.tool()
def set_task_reminder(task_id: int, remind_at: str, recurrence: str = "none", sound: bool = True) -> dict:
    """Set (or replace) the reminder on an existing task. A task can only have
    one active reminder -- this deactivates any previous one on the same task."""
    if recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    data, err = _request("POST", f"/tasks/{task_id}/reminder", json={
        "remind_at": remind_at, "recurrence": recurrence, "sound": sound,
    })
    return {"error": err} if err else data


@server.tool()
def remove_task_reminder(task_id: int) -> dict:
    """Deactivate the reminder on a task, if it has one."""
    data, err = _request("DELETE", f"/tasks/{task_id}/reminder")
    return {"error": err} if err else data


@server.tool()
def create_reminder(title: str, remind_at: str, note: str = "",
                     reminder_type: str = "general", recurrence: str = "none", sound: bool = True) -> dict:
    """Create a new standalone reminder (not tied to any task)."""
    if reminder_type not in REMINDER_TYPES:
        return {"error": f"Invalid reminder_type '{reminder_type}'. Must be one of: {', '.join(REMINDER_TYPES)}"}
    if recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    data, err = _request("POST", "/standalone-reminders", json={
        "title": title, "note": note, "reminder_type": reminder_type,
        "remind_at": remind_at, "recurrence": recurrence, "sound": sound,
    })
    return {"error": err} if err else data


@server.tool()
def update_reminder(reminder_id: int, title: str = None, note: str = None, remind_at: str = None,
                     reminder_type: str = None, recurrence: str = None, sound: bool = None) -> dict:
    """Update a standalone reminder. Only the fields you pass are changed."""
    if reminder_type is not None and reminder_type not in REMINDER_TYPES:
        return {"error": f"Invalid reminder_type '{reminder_type}'. Must be one of: {', '.join(REMINDER_TYPES)}"}
    if recurrence is not None and recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    payload = {k: v for k, v in {
        "title": title, "note": note, "remind_at": remind_at,
        "reminder_type": reminder_type, "recurrence": recurrence, "sound": sound,
    }.items() if v is not None}
    if not payload:
        return {"error": "Nothing to update -- pass at least one field."}
    data, err = _request("PUT", f"/standalone-reminders/{reminder_id}", json=payload)
    return {"error": err} if err else data


@server.tool()
def delete_reminder(reminder_id: int) -> dict:
    """Permanently delete a standalone reminder."""
    data, err = _request("DELETE", f"/standalone-reminders/{reminder_id}")
    return {"error": err} if err else data


@server.tool()
def acknowledge_reminder(reminder_id: int, kind: str, snooze_minutes: int = None) -> dict:
    """Dismiss or snooze a reminder that has fired. kind must be 'task' or
    'standalone' (as returned by list_reminders/get_due_reminders). Pass
    snooze_minutes to snooze instead of dismissing; omit it to dismiss (a
    non-recurring reminder is deactivated, a recurring one advances to its
    next occurrence)."""
    if kind not in ("task", "standalone"):
        return {"error": "kind must be 'task' or 'standalone'."}
    path = f"/reminders/{reminder_id}/acknowledge" if kind == "task" else f"/standalone-reminders/{reminder_id}/acknowledge"
    payload = {"snooze_minutes": snooze_minutes} if snooze_minutes else {}
    data, err = _request("POST", path, json=payload)
    return {"error": err} if err else data


if __name__ == "__main__":
    # Claude Desktop's Settings > Developer > "Local MCP servers" launches this
    # script itself as a subprocess and talks to it over stdio.
    server.run(transport="stdio")
