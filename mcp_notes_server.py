"""MCP server exposing this app's Notes (note_books / note_chapters / note_pages)
to Claude Desktop as a custom connector.

This is a thin client over the existing Flask HTTP API (task_manager.py's
/notes/* routes) -- it does not touch the database directly, so it can never
drift from the app's own validation/ordering/cascading logic, and it requires
the taskflow app to be running (default http://localhost:5001, override with
the TASKFLOW_API_URL env var).

Tools are split into read/search/create (unrestricted) and two distinct write
styles for existing content:
  - edit_note_fragment: a targeted find/replace, rejected if `find` isn't an
    exact, unique match in the current body. Prefer this for any change that
    isn't a full rewrite.
  - replace_note_body / replace_note_title: full overwrite of a page.
No delete tools are exposed for books/chapters/pages -- destructive structural
changes were out of scope for what was asked; add them later if needed.
"""

import html
import os
import re
import requests

from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("TASKFLOW_API_URL", "http://localhost:5001").rstrip("/")
TIMEOUT = 10
DIAGRAM_COLORS = ["blue", "green", "yellow", "red", "purple", "pink", "teal", "default"]

server = MCPServer(
    name="taskflow-notes",
    instructions=(
        "Tools for reading, searching, and editing the user's personal notes "
        "(organized as Notebooks > Chapters > Pages) in their local taskflow app. "
        "Page bodies are HTML using a small component vocabulary (div.nx-card, "
        "nx-header, nx-section-num, nx-def-row, pre.nx-code, div.nx-callout, "
        "nx-diagram-box with a nx-mermaid-source child for diagrams) as well as "
        "plain HTML (p/h1-h4/ul/ol/li/etc) for older or hand-written pages -- match "
        "whichever style a page already uses rather than forcing one style onto it. "
        "For any change to existing content that isn't a full rewrite, prefer "
        "edit_note_fragment over replace_note_body: it can only change the exact "
        "text you point it at and will refuse rather than guess, so it cannot "
        "accidentally wipe unrelated content. "
        "Notebook/chapter/page TITLES are always plain text, not HTML -- pass raw "
        "characters like '&' directly, never HTML-entity-encode them (never send "
        "\"&amp;\" for \"&\"). "
        "To add a flowchart, block diagram, mind map, or any other Mermaid diagram "
        "to a page, use add_diagram -- it builds the exact wrapper HTML this app's "
        "renderer requires, so don't hand-write a nx-diagram-box via "
        "edit_note_fragment/append_to_note yourself. Diagrams only render as an "
        "actual chart in the app's Read Mode (not the edit view) -- mention that to "
        "the user after adding one so they know to toggle it."
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


def _html_to_text(raw_html):
    import re
    import html
    text = re.sub(r"<[^>]+>", " ", raw_html or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _find_page(page_id):
    """No single-page GET route exists -- walk the nested notebook tree."""
    data, err = _request("GET", "/notes/books")
    if err:
        return None, None, None, err
    for book in data:
        for chapter in book.get("chapters", []):
            for page in chapter.get("pages", []):
                if page["id"] == page_id:
                    return page, chapter, book, None
    return None, None, None, f"No note page with id {page_id}."


@server.tool()
def list_notebooks() -> dict:
    """List every notebook, its chapters, and its pages (titles and ids only,
    no body content -- use get_note or search_notes to read actual content).
    Use this first to find the page id you need for other tools."""
    data, err = _request("GET", "/notes/books")
    if err:
        return {"error": err}
    return {
        "notebooks": [
            {
                "id": b["id"],
                "title": b["title"],
                "chapters": [
                    {
                        "id": c["id"],
                        "title": c["title"],
                        "pages": [{"id": p["id"], "title": p["title"]} for p in c.get("pages", [])],
                    }
                    for c in b.get("chapters", [])
                ],
            }
            for b in data
        ]
    }


@server.tool()
def search_notes(query: str) -> dict:
    """Case-insensitive search for `query` across every note page's title and
    body text. Returns matching pages with a short snippet of surrounding text."""
    data, err = _request("GET", "/notes/books")
    if err:
        return {"error": err}
    q = query.lower().strip()
    if not q:
        return {"error": "query must not be empty"}
    matches = []
    for book in data:
        for chapter in book.get("chapters", []):
            for page in chapter.get("pages", []):
                title = page.get("title") or ""
                text = _html_to_text(page.get("body") or "")
                hay = f"{title}\n{text}".lower()
                idx = hay.find(q)
                if idx == -1:
                    continue
                start = max(0, idx - 60)
                snippet = ("…" if start > 0 else "") + hay[start:idx + len(q) + 60].strip() + "…"
                matches.append({
                    "page_id": page["id"],
                    "title": title,
                    "notebook": book["title"],
                    "chapter": chapter["title"],
                    "snippet": snippet,
                })
    return {"query": query, "matches": matches}


@server.tool()
def get_note(page_id: int) -> dict:
    """Get one note page's full title and raw HTML body, plus which notebook
    and chapter it's in."""
    page, chapter, book, err = _find_page(page_id)
    if err:
        return {"error": err}
    return {
        "page_id": page["id"],
        "title": page["title"],
        "body_html": page.get("body") or "",
        "notebook": book["title"],
        "chapter": chapter["title"],
        "color": page.get("color"),
        "pinned": bool(page.get("pinned")),
    }


@server.tool()
def create_notebook(title: str, color: str = "default") -> dict:
    """Create a new, empty notebook. color is a UI accent name (e.g. 'blue',
    'green', 'default') -- any value is accepted, it's cosmetic only."""
    data, err = _request("POST", "/notes/books", json={"title": title, "color": color})
    return {"error": err} if err else data


@server.tool()
def create_chapter(book_id: int, title: str) -> dict:
    """Create a new chapter inside an existing notebook."""
    data, err = _request("POST", f"/notes/books/{book_id}/chapters", json={"title": title})
    return {"error": err} if err else data


@server.tool()
def create_note(chapter_id: int, title: str, body_html: str = "") -> dict:
    """Create a new page inside an existing chapter. body_html may be empty
    (create the page first, fill it in with a separate edit) or full content."""
    data, err = _request("POST", f"/notes/chapters/{chapter_id}/pages",
                          json={"title": title, "body": body_html})
    return {"error": err} if err else data


@server.tool()
def edit_note_fragment(page_id: int, find: str, replace: str) -> dict:
    """Make a targeted edit to ONE existing page: replace the exact HTML/text
    given in `find` with `replace`, leaving the rest of the page untouched.

    `find` must match the page's current body_html (from get_note)
    character-for-character, and must occur exactly once -- copy it verbatim,
    don't retype it from memory, and keep it as small as the smallest element
    that fully contains the point being changed (e.g. one <p>...</p> or one
    <span class="nx-def-text">...</span>), not a whole section or the whole
    page. If it doesn't match, or matches more than once, this fails with an
    error instead of guessing -- widen `find` with a bit more surrounding
    context and try again."""
    page, _, _, err = _find_page(page_id)
    if err:
        return {"error": err}
    body = page.get("body") or ""
    count = body.count(find) if find else 0
    if count == 0:
        return {"error": "`find` was not found in the page's current body_html. Re-check it against get_note's output -- it must match exactly."}
    if count > 1:
        return {"error": f"`find` matches {count} places in the page, so the edit is ambiguous. Include more surrounding text to make it unique."}
    new_body = body.replace(find, replace, 1)
    data, err = _request("PUT", f"/notes/pages/{page_id}", json={"body": new_body})
    return {"error": err} if err else {"page_id": page_id, "updated": True}


@server.tool()
def append_to_note(page_id: int, html_to_append: str) -> dict:
    """Add new content to the end of an existing page without touching what's
    already there."""
    page, _, _, err = _find_page(page_id)
    if err:
        return {"error": err}
    new_body = (page.get("body") or "") + html_to_append
    data, err = _request("PUT", f"/notes/pages/{page_id}", json={"body": new_body})
    return {"error": err} if err else {"page_id": page_id, "updated": True}


@server.tool()
def replace_note_title(page_id: int, title: str) -> dict:
    """Rename a page. Does not touch its body content."""
    data, err = _request("PUT", f"/notes/pages/{page_id}", json={"title": title})
    return {"error": err} if err else data


@server.tool()
def replace_note_body(page_id: int, body_html: str) -> dict:
    """Overwrite a page's ENTIRE body with new content, discarding whatever
    was there before. Only use this for a genuine full rewrite the user asked
    for (e.g. "draft a new page about X" on an empty/placeholder page, or
    "completely redo this page as..."); for any smaller change, use
    edit_note_fragment or append_to_note instead so unrelated content survives."""
    page, _, _, err = _find_page(page_id)
    if err:
        return {"error": err}
    data, err = _request("PUT", f"/notes/pages/{page_id}", json={"body": body_html})
    return {"error": err} if err else {"page_id": page_id, "updated": True}


@server.tool()
def add_diagram(page_id: int, mermaid_source: str, color: str = "blue", position: str = "append") -> dict:
    """Insert a Mermaid diagram into a note page. This covers flowcharts, block
    diagrams (via subgraphs), mind maps, sequence diagrams, and anything else
    Mermaid syntax supports -- the diagram TYPE is just whatever
    `mermaid_source` starts with (e.g. "flowchart TD", "mindmap",
    "sequenceDiagram"). Colored flowcharts work via ordinary Mermaid
    `style`/`classDef` directives inside `mermaid_source` itself.

    mermaid_source: raw Mermaid syntax with real newlines between lines (not
    "<br>" tags and not "\\n" escapes) -- write it exactly as you would in a
    standalone .mmd file. Do not HTML-escape it; pass raw characters.
    color: the diagram box's accent border color -- one of blue, green,
    yellow, red, purple, pink, teal, default.
    position: "append" (default) adds the diagram to the end of the page's
    existing content. "replace_body" makes the diagram the page's ENTIRE
    content, discarding whatever was there -- only use this if the page is
    empty or the user explicitly asked to replace everything.

    The diagram only renders as an actual chart in the app's Read Mode, not
    the edit view -- tell the user to toggle that if they ask why they don't
    see it rendered.
    """
    if color not in DIAGRAM_COLORS:
        return {"error": f"Invalid color '{color}'. Must be one of: {', '.join(DIAGRAM_COLORS)}"}
    if position not in ("append", "replace_body"):
        return {"error": "position must be 'append' or 'replace_body'."}
    if not mermaid_source or not mermaid_source.strip():
        return {"error": "mermaid_source must not be empty."}

    src = re.sub(r"<br\s*/?>", "\n", mermaid_source, flags=re.IGNORECASE)
    block = (
        f'<div class="nx-diagram-box accent-{color}" contenteditable="false">'
        f'<pre class="nx-mermaid-source">{html.escape(src)}</pre>'
        f'<div class="nx-diagram-placeholder">Diagram - view in Read Mode</div></div>'
    )

    page, _, _, err = _find_page(page_id)
    if err:
        return {"error": err}

    new_body = block if position == "replace_body" else (page.get("body") or "") + block
    data, err = _request("PUT", f"/notes/pages/{page_id}", json={"body": new_body})
    return {"error": err} if err else {"page_id": page_id, "updated": True}


if __name__ == "__main__":
    # Claude Desktop's Settings > Developer > "Local MCP servers" launches this
    # script itself as a subprocess and talks to it over stdio -- no port, no
    # cert, no manually keeping a server process alive required.
    server.run(transport="stdio")
