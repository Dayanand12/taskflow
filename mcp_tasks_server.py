"""MCP server exposing this app's standalone to-do Tasks (task_type='general'
with no step_id -- i.e. NOT a Workflow container and NOT an action-item nested
under a Workflow step) and their Subtasks to Claude Desktop as a custom
connector.

This is a thin client over the existing Flask HTTP API (task_manager.py's
/tasks and /subtasks routes) -- it does not touch the database directly, so
it can never drift from the app's own validation/enrichment logic, and it
requires the taskflow app to be running (default http://localhost:5001,
override with the TASKFLOW_API_URL env var).

Scope is deliberately just standalone tasks + their subtasks -- mirrors
taskflow-workflows' own scoping note. Tags, task dependencies, and time
tracking are all out of scope (wasn't asked for; add later if needed).
Workflow container tasks and step-linked action items are handled by the
separate taskflow-workflows connector, not here.
"""

import os
import requests

from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("TASKFLOW_API_URL", "http://localhost:5001").rstrip("/")
TIMEOUT = 10

STATUSES = ["not_started", "todo", "in_process", "hold", "completed", "cancelled"]
PRIORITIES = ["low", "medium", "high"]
RECURRENCES = ["none", "daily", "weekdays", "weekly", "biweekly", "monthly"]

server = MCPServer(
    name="taskflow-tasks",
    instructions=(
        "Tools for reading and managing the user's standalone to-do Tasks "
        "(and their Subtask checklists) in their local taskflow app -- this "
        "does NOT include Workflow steps/action-items, use the "
        "taskflow-workflows connector for those. "
        f"Valid task statuses: {', '.join(STATUSES)}. Valid priorities: "
        f"{', '.join(PRIORITIES)}. Valid recurrence values: {', '.join(RECURRENCES)} "
        "-- when a recurring task is marked completed, the app automatically "
        "spawns the next occurrence, so don't create it yourself. "
        "due_date is 'YYYY-MM-DD', due_time is 'HH:MM', both optional. "
        "All title/description text fields are stored and displayed as plain "
        "text, NOT HTML -- pass raw characters like '&', '<', \"'\" directly, "
        "never HTML-entity-encode them."
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


def _is_standalone(t):
    return t.get("task_type", "general") == "general" and not t.get("step_id")


def _slim(t):
    return {
        "id": t["id"], "title": t["title"], "status": t["status"], "priority": t.get("priority"),
        "due_date": t.get("due_date"), "due_time": t.get("due_time"), "project": t.get("project"),
        "recurrence": t.get("recurrence"),
        "subtasks_done": t.get("subtask_done", 0), "subtasks_total": t.get("subtask_total", 0),
    }


def _find_task(task_id):
    data, err = _request("GET", "/tasks")
    if err:
        return None, err
    for t in data:
        if t["id"] == task_id and _is_standalone(t):
            return t, None
    return None, f"No standalone task with id {task_id}."


@server.tool()
def list_tasks(status: str = None, project: str = None) -> dict:
    """List standalone to-do tasks (not Workflow steps/action-items). Optionally
    filter by exact status and/or project name. Omit both to list everything."""
    if status is not None and status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {', '.join(STATUSES)}"}
    data, err = _request("GET", "/tasks")
    if err:
        return {"error": err}
    tasks = [t for t in data if _is_standalone(t)]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if project:
        tasks = [t for t in tasks if (t.get("project") or "") == project]
    return {"tasks": [_slim(t) for t in tasks]}


@server.tool()
def search_tasks(query: str) -> dict:
    """Case-insensitive search for `query` across standalone tasks' titles and
    descriptions."""
    q = (query or "").lower().strip()
    if not q:
        return {"error": "query must not be empty"}
    data, err = _request("GET", "/tasks")
    if err:
        return {"error": err}
    matches = [
        _slim(t) for t in data
        if _is_standalone(t) and (q in t["title"].lower() or q in (t.get("description") or "").lower())
    ]
    return {"query": query, "matches": matches}


@server.tool()
def get_task(task_id: int) -> dict:
    """Get one standalone task's full detail: all fields, tags, and its
    subtask checklist (title + done state, in order)."""
    task, err = _find_task(task_id)
    if err:
        return {"error": err}
    subs, err = _request("GET", f"/tasks/{task_id}/subtasks")
    if err:
        return {"error": err}
    out = _slim(task)
    out.update({
        "description": task.get("description") or "",
        "tags": [tg["name"] for tg in task.get("tags", [])],
        "subtasks": [{"id": s["id"], "title": s["title"], "is_done": bool(s["is_done"])} for s in subs],
    })
    return out


@server.tool()
def create_task(title: str, description: str = "", priority: str = "medium",
                 due_date: str = None, due_time: str = None, project: str = None,
                 recurrence: str = "none") -> dict:
    """Create a new standalone to-do task."""
    if priority not in PRIORITIES:
        return {"error": f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"}
    if recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    data, err = _request("POST", "/tasks", json={
        "title": title, "description": description, "priority": priority,
        "due_date": due_date, "due_time": due_time, "project": project,
        "recurrence": recurrence, "task_type": "general",
    })
    return {"error": err} if err else _slim(data)


@server.tool()
def update_task(task_id: int, title: str = None, description: str = None, status: str = None,
                 priority: str = None, due_date: str = None, due_time: str = None,
                 project: str = None, recurrence: str = None) -> dict:
    """Update a standalone task. Only the fields you pass are changed."""
    if status is not None and status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {', '.join(STATUSES)}"}
    if priority is not None and priority not in PRIORITIES:
        return {"error": f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"}
    if recurrence is not None and recurrence not in RECURRENCES:
        return {"error": f"Invalid recurrence '{recurrence}'. Must be one of: {', '.join(RECURRENCES)}"}
    task, err = _find_task(task_id)
    if err:
        return {"error": err}
    payload = {k: v for k, v in {
        "title": title, "description": description, "status": status, "priority": priority,
        "due_date": due_date, "due_time": due_time, "project": project, "recurrence": recurrence,
    }.items() if v is not None}
    if not payload:
        return {"error": "Nothing to update -- pass at least one field."}
    data, err = _request("PUT", f"/tasks/{task_id}", json=payload)
    return {"error": err} if err else _slim(data)


@server.tool()
def add_subtask(task_id: int, title: str) -> dict:
    """Add a new checklist item (subtask) to the end of a standalone task."""
    task, err = _find_task(task_id)
    if err:
        return {"error": err}
    data, err = _request("POST", f"/tasks/{task_id}/subtasks", json={"title": title})
    return {"error": err} if err else data


@server.tool()
def update_subtask(subtask_id: int, title: str = None, is_done: bool = None) -> dict:
    """Rename and/or check/uncheck a subtask. Only the fields you pass are changed."""
    payload = {}
    if title is not None:
        payload["title"] = title
    if is_done is not None:
        payload["is_done"] = is_done
    if not payload:
        return {"error": "Nothing to update -- pass title and/or is_done."}
    data, err = _request("PUT", f"/subtasks/{subtask_id}", json=payload)
    return {"error": err} if err else data


if __name__ == "__main__":
    # Claude Desktop's Settings > Developer > "Local MCP servers" launches this
    # script itself as a subprocess and talks to it over stdio.
    server.run(transport="stdio")
