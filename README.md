# Kanban Boards

A lightweight, local-first kanban board web app. No framework, no package manager, no build step. Runs entirely on Python's standard library with SQLite as the database.

---

## Requirements

- Python 3.8+

That's it.

---

## Running

```bash
python3 app.py           # starts on port 8000
python3 app.py 9000      # starts on a specific port
```

Open the printed URL in your browser. The SQLite database (`kanban.db`) is created automatically on first run if it doesn't exist.

If the requested port is already in use, the server automatically increments until it finds a free one and prints the actual URL it bound to.

To stop the server: `Ctrl+C`.

---

## Project Structure

```
kanban-boards/
├── app.py              # HTTP server, request routing, all API handlers, DB init
├── migrate.py          # Schema migration script — safe to run on any existing DB
├── seed.py             # Populates the DB with dummy sprints and cards for testing
├── kanban.db           # SQLite database (auto-created, gitignore this)
└── static/
    ├── index.html      # Single-page shell — markup only, no logic
    ├── style.css       # All styles
    └── app.js          # All frontend logic — state, rendering, drag-and-drop, API calls
```

---

## Architecture

### Backend (`app.py`)

The server is built on Python's `http.server.BaseHTTPRequestHandler` with no third-party dependencies. Every HTTP verb gets its own `do_<VERB>` method (`do_GET`, `do_POST`, `do_PUT`, `do_DELETE`), each of which manually dispatches to a handler function via `re.match` on the path.

**Request lifecycle:**
1. `do_<VERB>` receives the request and parses the path with `urllib.parse.urlparse`
2. A regex match against the path determines which handler to call (e.g. `/api/cards/(\d+)`)
3. The handler reads the JSON body via `read_json()` (uses `Content-Length` header to read exactly N bytes)
4. Opens a fresh SQLite connection, executes the query, commits, closes
5. Sends the response via `send_json()` which sets `Content-Type: application/json` and `Content-Length`

Static files (`/`, `/static/*`) are served by reading from the `static/` directory relative to `app.py`. Path traversal is blocked by comparing `os.path.abspath` of the resolved path against the static directory.

**Port selection** is handled at startup via `argparse`. The port argument is optional and positional (`python3 app.py 9000`). After parsing, `find_open_port()` uses `socket.bind()` to verify the port is actually free — if not, it increments until it finds one. This means a requested port is always honoured if available, and the fallback is automatic otherwise.

**Why no Flask?** Zero installations means the app runs on any machine with Python 3.8+ and nothing else — no venv, no pip, no internet access required.

### Database (`kanban.db`)

SQLite via Python's built-in `sqlite3` module. The schema is initialized with `CREATE TABLE IF NOT EXISTS`, so the first run creates the tables and subsequent runs are no-ops.

**Schema:**

```sql
CREATE TABLE sprints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cards (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id    INTEGER NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'Not Triaged',
    priority     TEXT NOT NULL DEFAULT 'Medium',
    position     INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_on       TEXT,
    delivered_on TEXT,
    notes        TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (sprint_id) REFERENCES sprints(id) ON DELETE CASCADE
);

CREATE TABLE card_dependencies (
    card_id    INTEGER NOT NULL,
    depends_on INTEGER NOT NULL,
    PRIMARY KEY (card_id, depends_on),
    FOREIGN KEY (card_id)    REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on) REFERENCES cards(id) ON DELETE CASCADE
);
```

`PRAGMA foreign_keys = ON` is set on every connection so `ON DELETE CASCADE` is enforced — deleting a sprint deletes all its cards; deleting a card removes all its dependency rows.

`due_on` and `delivered_on` are stored as ISO 8601 date strings (`YYYY-MM-DD`) or `NULL` if unset. `notes` is a freeform text field for status updates and running commentary, kept separate from `description` so the original scope statement stays intact.

`init_db()` also runs `ALTER TABLE` migrations on every boot, wrapped in `try/except` — this is a no-op on a current DB and a silent migration on any older DB missing those columns.

`position` is an integer used to order cards within a column. When a card is created, `position` is set to `MAX(position) + 1` within that sprint+status bucket. When a card is dragged to a new column, only the `status` field is updated.

All connections use `row_factory = sqlite3.Row`, which allows columns to be accessed by name and converted to `dict` for JSON serialization.

### REST API

All endpoints consume and produce `application/json`.

| Method   | Path                              | Description                                                                 |
|----------|-----------------------------------|-----------------------------------------------------------------------------|
| `GET`    | `/api/sprints`                    | List all sprints, ordered by `created_at DESC`                              |
| `POST`   | `/api/sprints`                    | Create a sprint `{ name }`                                                  |
| `PUT`    | `/api/sprints/:id`                | Rename a sprint `{ name }`                                                  |
| `DELETE` | `/api/sprints/:id`                | Delete sprint and all its cards                                             |
| `GET`    | `/api/sprints/:id/cards`          | List cards for a sprint, ordered by `position, id`                          |
| `POST`   | `/api/sprints/:id/cards`          | Create a card `{ title, description?, status?, priority?, due_on?, delivered_on?, notes? }` |
| `PUT`    | `/api/cards/:id`                  | Update any card fields (edits and drag-and-drop status changes)             |
| `DELETE` | `/api/cards/:id`                  | Delete a card                                                               |
| `GET`    | `/api/sprints/:id/dependencies`   | List all dependency pairs `{ card_id, depends_on }` for a sprint            |
| `GET`    | `/api/cards/:id/dependencies`     | Get predecessors and successors for a card `{ predecessors, successors }`   |
| `POST`   | `/api/dependencies`               | Create a dependency `{ card_id, depends_on }` — rejects cycles (409)       |
| `DELETE` | `/api/dependencies/:card_id/:depends_on` | Remove a specific dependency                                        |

The `PUT /api/cards/:id` handler merges the incoming payload over the existing row — any fields not included retain their current values. This means both full edits (from the modal) and partial updates (drag-and-drop only sends `status`) go through the same endpoint.

Status values are validated against the canonical list on writes; invalid values fall back to the existing value (on update) or `Not Triaged` (on create). Same pattern for `priority`.

**Cycle detection:** Before inserting a dependency, the server runs a BFS from the proposed `depends_on` node following existing forward edges. If it reaches `card_id`, the new edge would form a cycle and the request is rejected with a 409.

### Frontend (`app.js`)

The frontend is a single vanilla JS file. There is no framework, no component model, and no build step. The entire UI is re-rendered from scratch on any state change, which is cheap enough at this data scale.

**State:**

```js
const state = {
  sprints: [],           // all sprints from the server
  currentSprintId: null,
  cards: [],             // cards for the current sprint
  deps: [],              // dependency pairs [{card_id, depends_on}] for the current sprint
  view: 'kanban',        // 'kanban' | 'gantt'
  editingCardId: null,   // null = creating new card
  sprintModalMode: null  // 'create' | 'rename'
};
```

**Boot sequence:**

1. `DOMContentLoaded` fires, calls `loadSprints()`
2. `loadSprints()` fetches `/api/sprints`, populates `state.sprints`, renders the sprint `<select>`
3. If any sprints exist, auto-selects the first (most recent) by calling `selectSprint(id)`
4. `selectSprint()` fetches cards and dependencies in parallel via `Promise.all`, then renders the active view

**Rendering — Board:**

`renderBoard()` wipes `#board` and rebuilds the DOM from scratch each time. For each status it creates a `.column` div, filters `state.cards` to that status, sorts by `position`, and appends a `.card` element per card via `buildCard()`. Columns use `flex: 1 1 0` so they always share the available width evenly — no horizontal scroll.

**Rendering — Gantt:**

`renderGantt()` builds a CSS Grid layout with a sticky label sidebar and a scrollable date grid. The date range is computed from the earliest to the latest `due_on` across all cards, padded by a few days on each side and floored at 30 days. Cards are sorted via `topoSort()` (Kahn's algorithm on the dependency graph) so predecessors always appear above their dependents.

Each card with a `due_on` gets an SVG pill centred on its due date column. Dependency arrows are rendered as SVG cubic Bézier curves connecting the right edge of a predecessor pill to the left edge of the dependent pill. Each arrow is rendered as two overlapping paths: a 1.5px dashed visible stroke and a 12px transparent stroke that acts as a wider click target.

**Drag and drop — board:**

Uses the native HTML5 Drag and Drop API. `dragstart` stores `card.id` in `dataTransfer`; `drop` on a column zone reads the ID and calls `updateCard` with the new status.

**Drag and drop — Gantt dependency drawing:**

Each pill has two circular drag handles (left and right edges) that appear on hover. Dragging from the **left handle** draws a rubber-band line from the cursor toward the pill, creating a predecessor relationship on drop (the dragged card depends on the target). Dragging from the **right handle** draws the line outward from the pill toward the cursor, creating a successor relationship on drop (the target card depends on the dragged card). A `hasMoved` flag distinguishes a drag gesture from a stationary click, which opens the card modal instead.

**Modals:**

Two modals share the same pattern: an overlay `div` is toggled via the `.hidden` class. Clicking the overlay background, pressing `Escape`, or clicking Cancel closes them. Pressing `Enter` (outside a `<textarea>`) saves.

The card modal is dual-purpose: `editingCardId === null` means "create new", anything else means "edit existing". For existing cards, a Dependencies section lists all predecessors and successors. Clicking `×` on a dependency **stages** the deletion locally — it is not committed to the server until Save is clicked. Cancelling the modal discards all staged deletions.

**HTML escaping:**

User-supplied strings inserted into the DOM via `innerHTML` are passed through `esc()`, which escapes `&`, `<`, `>`, and `"` to prevent XSS.

---

## Statuses & Priorities

**Statuses** (column order left to right):

| Status          | Colour  |
|-----------------|---------|
| Not Triaged     | Grey    |
| Backlog         | Indigo  |
| Blocked         | Red     |
| In Progress     | Blue    |
| Needs Review    | Amber   |
| Ready Playback  | Purple  |
| On Standby      | Light grey |
| Done            | Green   |

**Priorities** (indicated by a coloured dot on each card):
- Low — green
- Medium — amber
- High — red

---

## Schema Migrations (`migrate.py`)

`migrate.py` is a standalone migration script for upgrading existing databases without data loss. It is safe to run multiple times — each migration checks for the presence of the column or table before applying it.

```bash
python3 migrate.py
```

Migrations covered:

| Migration | Change |
|-----------|--------|
| v1 → v2 | `cards.due_on`, `cards.delivered_on` columns |
| v2 → v3 | `cards.notes` column |
| v3 → v4 | `card_dependencies` table |

Fresh databases created by `app.py` already include all of these — the script is only needed when upgrading an instance that predates one or more of these changes.

---

## Data Persistence

The database is a single file (`kanban.db`) in the project root. It is not backed up or replicated — if you delete it, all data is gone. For a local planning tool this is intentional; the tradeoff is zero infrastructure.

If you want to back up your data:

```bash
cp kanban.db kanban.db.bak
```

Or export to JSON at any time by querying SQLite directly:

```bash
sqlite3 -json kanban.db "SELECT * FROM cards;" > cards_export.json
```

---

## Seeding Dummy Data

`seed.py` populates the database with 3 sprints, 14 cards, and 10 dependency relationships. Due dates are computed relative to the date the script is run, so the Gantt chart always shows a realistic rolling window. The script wipes all existing data before inserting, so re-running it always produces a clean state.

```bash
python3 seed.py
```

For a full reset from scratch:

```bash
rm kanban.db && python3 seed.py
```
