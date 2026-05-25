# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.0",
# ]
# ///

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("KANBAN_URL", "http://localhost:8000")
CHUNK_SIZE = int(os.environ.get("KANBAN_BULK_CHUNK", "50"))

mcp = FastMCP("Kanban Boards")


def _call(method: str, path: str, body=None):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read())
        raise ValueError(payload.get("error", str(e)))


def _chunked(lst: list):
    for i in range(0, len(lst), CHUNK_SIZE):
        yield lst[i : i + CHUNK_SIZE]


# ── Sprint tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def list_sprints() -> list:
    """List all sprints, ordered newest first."""
    return _call("GET", "/api/sprints")


@mcp.tool()
def create_sprint(name: str) -> dict:
    """Create a new sprint. Returns the created sprint object."""
    return _call("POST", "/api/sprints", {"name": name})


@mcp.tool()
def update_sprint(sprint_id: int, name: str) -> dict:
    """Rename a sprint. Returns the updated sprint object."""
    return _call("PUT", f"/api/sprints/{sprint_id}", {"name": name})


@mcp.tool()
def delete_sprint(sprint_id: int) -> dict:
    """Delete a sprint and all its cards. Returns {ok: true}."""
    return _call("DELETE", f"/api/sprints/{sprint_id}")


# ── Card tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_cards(sprint_id: int) -> list:
    """List all cards in a sprint, ordered by position."""
    return _call("GET", f"/api/sprints/{sprint_id}/cards")


@mcp.tool()
def create_card(
    sprint_id: int,
    title: str,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_on: Optional[str] = None,
    delivered_on: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Create a card in a sprint.

    status: 'Not Triaged' | 'Backlog' | 'Blocked' | 'In Progress' |
            'Needs Review' | 'Ready Playback' | 'On Standby' | 'Done'
    priority: 'Low' | 'Medium' | 'High'
    due_on / delivered_on: ISO 8601 date string (YYYY-MM-DD)
    """
    body: dict = {"title": title}
    if description is not None:
        body["description"] = description
    if status is not None:
        body["status"] = status
    if priority is not None:
        body["priority"] = priority
    if due_on is not None:
        body["due_on"] = due_on
    if delivered_on is not None:
        body["delivered_on"] = delivered_on
    if notes is not None:
        body["notes"] = notes
    return _call("POST", f"/api/sprints/{sprint_id}/cards", body)


@mcp.tool()
def update_card(
    card_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_on: Optional[str] = None,
    delivered_on: Optional[str] = None,
    notes: Optional[str] = None,
    sprint_id: Optional[int] = None,
    position: Optional[int] = None,
) -> dict:
    """Update any fields of a card — only provided fields are changed.

    Set sprint_id to move the card to a different sprint.
    status / priority / due_on: same values as create_card.
    """
    body: dict = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if status is not None:
        body["status"] = status
    if priority is not None:
        body["priority"] = priority
    if due_on is not None:
        body["due_on"] = due_on
    if delivered_on is not None:
        body["delivered_on"] = delivered_on
    if notes is not None:
        body["notes"] = notes
    if sprint_id is not None:
        body["sprint_id"] = sprint_id
    if position is not None:
        body["position"] = position
    return _call("PUT", f"/api/cards/{card_id}", body)


@mcp.tool()
def delete_card(card_id: int) -> dict:
    """Delete a card and all its dependency edges. Returns {ok: true}."""
    return _call("DELETE", f"/api/cards/{card_id}")


# ── Dependency tools ──────────────────────────────────────────────────────────

@mcp.tool()
def list_sprint_dependencies(sprint_id: int) -> list:
    """List all dependency pairs for cards in a sprint.

    Returns [{card_id, depends_on}, ...] where card_id depends on depends_on.
    """
    return _call("GET", f"/api/sprints/{sprint_id}/dependencies")


@mcp.tool()
def get_card_dependencies(card_id: int) -> dict:
    """Get predecessors and successors of a card.

    Returns {predecessors: [{id, title}], successors: [{id, title}]}.
    Predecessors are cards this card depends on; successors depend on this card.
    """
    return _call("GET", f"/api/cards/{card_id}/dependencies")


@mcp.tool()
def create_dependency(card_id: int, depends_on: int) -> dict:
    """Create a dependency: card_id cannot proceed until depends_on is done.

    Returns {ok: true} or raises an error if a cycle would be created.
    """
    return _call("POST", "/api/dependencies", {"card_id": card_id, "depends_on": depends_on})


@mcp.tool()
def delete_dependency(card_id: int, depends_on: int) -> dict:
    """Remove a dependency edge between two cards. Returns {ok: true}."""
    return _call("DELETE", f"/api/dependencies/{card_id}/{depends_on}")


# ── Bulk tools (auto-chunked) ─────────────────────────────────────────────────

@mcp.tool()
def bulk_update_cards(updates: list[dict]) -> dict:
    """Update multiple cards in one call. Handles lists of any size automatically.

    Each item must include 'id' plus any fields to change: title, description,
    status, priority, due_on, delivered_on, notes, sprint_id, position.

    Returns {updated: [...card objects...], errors: [{id, error}]}.
    Items with unknown ids appear in errors; the rest are still applied.
    """
    all_updated: list = []
    all_errors: list = []
    for chunk in _chunked(updates):
        result = _call("PATCH", "/api/cards/bulk", chunk)
        all_updated.extend(result.get("updated", []))
        all_errors.extend(result.get("errors", []))
    return {"updated": all_updated, "errors": all_errors}


@mcp.tool()
def bulk_move_cards(card_ids: list[int], sprint_id: int) -> dict:
    """Move multiple cards to a target sprint. Handles lists of any size automatically.

    Returns {moved: int, requested: int} aggregated across all chunks.
    """
    total_moved = 0
    total_requested = 0
    for chunk in _chunked(card_ids):
        result = _call("POST", "/api/cards/bulk-move", {"card_ids": chunk, "sprint_id": sprint_id})
        total_moved += result.get("moved", 0)
        total_requested += result.get("requested", len(chunk))
    return {"moved": total_moved, "requested": total_requested}


@mcp.tool()
def bulk_create_dependencies(dependencies: list[dict]) -> dict:
    """Create multiple dependency edges in one call. Handles lists of any size automatically.

    Each item: {card_id: int, depends_on: int}.
    Edges that would create cycles are skipped rather than aborting the batch.

    Returns {created: int, skipped: [{card_id, depends_on, reason}]}.
    """
    total_created = 0
    all_skipped: list = []
    for chunk in _chunked(dependencies):
        result = _call("POST", "/api/dependencies/bulk", chunk)
        total_created += result.get("created", 0)
        all_skipped.extend(result.get("skipped", []))
    return {"created": total_created, "skipped": all_skipped}


if __name__ == "__main__":
    mcp.run()
