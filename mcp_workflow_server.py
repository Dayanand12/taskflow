"""MCP server exposing this app's Workflows (tasks with task_type='workflow',
their task_steps, and the action-item tasks nested under each step) to Claude
Desktop as a custom connector.

This is a thin client over the existing Flask HTTP API (task_manager.py's
/tasks and /steps routes) -- it does not touch the database directly, so it
can never drift from the app's own validation/ordering logic, and it requires
the taskflow app to be running (default http://localhost:5001, override with
the TASKFLOW_API_URL env var).

Scope is deliberately just Workflows, not the whole task tracker (standalone
to-dos, subtasks, tags, dependencies, time tracking, reminders, meetings are
all out of scope) -- this mirrors exactly what the in-app Workflow AI
assistant used to operate on before it was replaced by this connector.

No delete tools are exposed for workflows/steps/tasks -- wasn't asked for,
easy to add later if needed. Unlike the Notes connector, there's no special
"targeted edit" tool here: task/step fields (title, status, description,
priority) are already small, structured, individually-addressable values, so
a normal partial update is inherently targeted -- there's no analogue to a
note's "whole HTML body" that a careless rewrite could wipe.
"""

import os
import requests

from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("TASKFLOW_API_URL", "http://localhost:5001").rstrip("/")
TIMEOUT = 10

STATUSES = ["not_started", "todo", "in_process", "hold", "completed", "cancelled"]
PRIORITIES = ["low", "medium", "high"]

server = MCPServer(
    name="taskflow-workflows",
    instructions=(
        "Tools for reading and managing the user's Workflows in their local taskflow "
        "app. A Workflow is a named goal broken into ordered Steps, and each Step "
        "contains concrete action-item Tasks. Steps are normally sequential, but two "
        "or more can be marked parallel so they run side-by-side (same stage) instead "
        "of one-after-another -- use add_parallel_step for those, not add_step. "
        f"Valid task/step statuses: {', '.join(STATUSES)}. Valid task priorities: "
        f"{', '.join(PRIORITIES)}. "
        "Use list_workflows to find a workflow's id, then get_workflow to see its "
        "full step/task breakdown (including each step's parallel_group) before "
        "adding to or changing it. "
        "All title/description text fields are stored and displayed as plain text, NOT "
        "HTML -- pass raw characters like '&', '<', \"'\" directly (e.g. \"Portfolio & P&L\"), "
        "never HTML-entity-encode them (never send \"&amp;\" for \"&\")."
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


def _slim_task(t):
    return {
        "id": t["id"], "title": t["title"], "status": t["status"], "priority": t.get("priority"),
        "description": t.get("description") or "",
        "due_date": t.get("due_date"), "due_time": t.get("due_time"),
    }


@server.tool()
def list_workflows() -> dict:
    """List every Workflow with its id, title, status, and step progress
    (no task-level detail -- use get_workflow for that)."""
    data, err = _request("GET", "/tasks")
    if err:
        return {"error": err}
    workflows = [t for t in data if t.get("task_type") == "workflow"]
    out = []
    for wf in workflows:
        steps, err = _request("GET", f"/tasks/{wf['id']}/steps")
        if err:
            return {"error": err}
        out.append({
            "id": wf["id"], "title": wf["title"], "status": wf["status"],
            "step_count": len(steps),
            "steps_done": sum(1 for s in steps if s["status"] == "completed"),
        })
    return {"workflows": out}


@server.tool()
def get_workflow(workflow_id: int) -> dict:
    """Get one Workflow's full detail: its own title/description/status, plus
    every step in order with the tasks nested under each step."""
    data, err = _request("GET", "/tasks")
    if err:
        return {"error": err}
    wf = next((t for t in data if t["id"] == workflow_id and t.get("task_type") == "workflow"), None)
    if not wf:
        return {"error": f"No workflow with id {workflow_id}."}
    steps, err = _request("GET", f"/tasks/{workflow_id}/steps")
    if err:
        return {"error": err}
    return {
        "id": wf["id"], "title": wf["title"], "status": wf["status"],
        "description": wf.get("description") or "",
        "steps": [
            {
                "id": s["id"], "title": s["title"], "status": s["status"],
                # Steps sharing the same non-null parallel_group run side-by-side in the
                # in-app Flow view instead of one-after-another -- see add_parallel_step.
                "parallel_group": s.get("parallel_group"),
                "tasks": [_slim_task(t) for t in s.get("tasks", [])],
            }
            for s in steps
        ],
    }


@server.tool()
def create_workflow(title: str, description: str = "") -> dict:
    """Create a new, empty Workflow (no steps yet -- use add_step to build it out)."""
    data, err = _request("POST", "/tasks", json={"title": title, "description": description, "task_type": "workflow"})
    return {"error": err} if err else data


@server.tool()
def update_workflow(workflow_id: int, title: str = None, description: str = None, status: str = None) -> dict:
    """Update a Workflow's own title, description, and/or status. Only the
    fields you pass are changed; omit a field to leave it as-is."""
    if status is not None and status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {', '.join(STATUSES)}"}
    payload = {k: v for k, v in {"title": title, "description": description, "status": status}.items() if v is not None}
    if not payload:
        return {"error": "Nothing to update -- pass at least one of title/description/status."}
    data, err = _request("PUT", f"/tasks/{workflow_id}", json=payload)
    return {"error": err} if err else data


@server.tool()
def add_step(workflow_id: int, title: str) -> dict:
    """Add a new sequential step to the end of a workflow's step list. For a
    step that should run alongside an existing one instead of after it, use
    add_parallel_step."""
    data, err = _request("POST", f"/tasks/{workflow_id}/steps", json={"title": title})
    return {"error": err} if err else data


@server.tool()
def add_parallel_step(step_id: int, title: str) -> dict:
    """Add a new step that runs in parallel with an existing step (same stage
    in the workflow, shown side-by-side in the in-app Flow view) rather than
    after it. Pass the id of the step the new one should run alongside --
    check get_workflow's `parallel_group` field first: if that step is
    already parallel with others (non-null parallel_group), the new step
    joins that same group; otherwise a new group is created for the two of
    them. Mirrors the "add parallel step" action in the app's own Flow view."""
    anchor, err = _request("GET", f"/steps/{step_id}")
    if err:
        return {"error": err}
    pg = anchor.get("parallel_group")
    if not pg:
        pg = f"pg{step_id}"
        _, err = _request("PUT", f"/steps/{step_id}", json={"parallel_group": pg})
        if err:
            return {"error": err}
    data, err = _request("POST", f"/tasks/{anchor['task_id']}/steps", json={
        "title": title, "parallel_group": pg, "position": anchor["position"],
    })
    return {"error": err} if err else data


@server.tool()
def update_step(step_id: int, title: str = None, status: str = None) -> dict:
    """Update a step's title and/or status. Only the fields you pass are
    changed. Completing/reopening a step does NOT cascade to its tasks --
    update those individually with update_task."""
    if status is not None and status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {', '.join(STATUSES)}"}
    payload = {k: v for k, v in {"title": title, "status": status}.items() if v is not None}
    if not payload:
        return {"error": "Nothing to update -- pass at least one of title/status."}
    data, err = _request("PUT", f"/steps/{step_id}", json=payload)
    return {"error": err} if err else data


@server.tool()
def add_task(step_id: int, title: str, description: str = "", priority: str = "medium") -> dict:
    """Add a new action-item task under an existing step."""
    if priority not in PRIORITIES:
        return {"error": f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"}
    data, err = _request("POST", "/tasks", json={
        "title": title, "description": description, "priority": priority, "step_id": step_id,
    })
    return {"error": err} if err else data


@server.tool()
def update_task(task_id: int, title: str = None, description: str = None, status: str = None, priority: str = None) -> dict:
    """Update a task's title, description, status, and/or priority. Only the
    fields you pass are changed."""
    if status is not None and status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Must be one of: {', '.join(STATUSES)}"}
    if priority is not None and priority not in PRIORITIES:
        return {"error": f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"}
    payload = {k: v for k, v in {
        "title": title, "description": description, "status": status, "priority": priority,
    }.items() if v is not None}
    if not payload:
        return {"error": "Nothing to update -- pass at least one of title/description/status/priority."}
    data, err = _request("PUT", f"/tasks/{task_id}", json=payload)
    return {"error": err} if err else data


if __name__ == "__main__":
    # Claude Desktop's Settings > Developer > "Local MCP servers" launches this
    # script itself as a subprocess and talks to it over stdio.
    server.run(transport="stdio")
