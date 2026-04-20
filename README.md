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
```

`PRAGMA foreign_keys = ON` is set on every connection so `ON DELETE CASCADE` is enforced — deleting a sprint deletes all its cards.

`due_on` and `delivered_on` are stored as ISO 8601 date strings (`YYYY-MM-DD`) or `NULL` if unset. `notes` is a freeform text field for status updates and running commentary, kept separate from `description` so the original scope statement stays intact.

`init_db()` also runs `ALTER TABLE cards ADD COLUMN` for `due_on`, `delivered_on`, and `notes` on every boot, wrapped in a `try/except` — this is a no-op on a current DB and a silent migration on any DB created before these columns were added.

`position` is an integer used to order cards within a column. When a card is created, `position` is set to `MAX(position) + 1` within that sprint+status bucket. When a card is dragged to a new column, only the `status` field is updated (position is appended to the end of the target column implicitly by the sort order).

All connections use `row_factory = sqlite3.Row`, which allows columns to be accessed by name and converted to `dict` for JSON serialization.

### REST API

All endpoints consume and produce `application/json`.

| Method   | Path                         | Description                              |
|----------|------------------------------|------------------------------------------|
| `GET`    | `/api/sprints`               | List all sprints, ordered by `created_at DESC` |
| `POST`   | `/api/sprints`               | Create a sprint `{ name }`              |
| `PUT`    | `/api/sprints/:id`           | Rename a sprint `{ name }`              |
| `DELETE` | `/api/sprints/:id`           | Delete sprint and all its cards          |
| `GET`    | `/api/sprints/:id/cards`     | List cards for a sprint, ordered by `position, id` |
| `POST`   | `/api/sprints/:id/cards`     | Create a card `{ title, description?, status?, priority?, due_on?, delivered_on?, notes? }` |
| `PUT`    | `/api/cards/:id`             | Update any card fields (used for edits and drag-and-drop status changes) |
| `DELETE` | `/api/cards/:id`             | Delete a card                            |

The `PUT /api/cards/:id` handler merges the incoming payload over the existing row — any fields not included in the request body retain their current values. This means both full edits (from the modal) and partial updates (drag-and-drop only sends `status`) go through the same endpoint.

Status values are validated against the canonical list on writes; invalid values fall back to the existing value (on update) or `Not Triaged` (on create). Same pattern for `priority` (`Low`, `Medium`, `High`).

### Frontend (`app.js`)

The frontend is a single vanilla JS file. There is no framework, no component model, and no build step. The entire UI is re-rendered from scratch on any state change (`renderBoard()`), which is cheap enough at this data scale.

**State:**

```js
const state = {
  sprints: [],          // all sprints from the server
  currentSprintId: null,
  cards: [],            // cards for the current sprint
  editingCardId: null,  // null = creating new card
  sprintModalMode: null // 'create' | 'rename'
};
```

**Boot sequence:**

1. `DOMContentLoaded` fires, calls `loadSprints()`
2. `loadSprints()` fetches `/api/sprints`, populates `state.sprints`, renders the sprint `<select>`
3. If any sprints exist, auto-selects the first (most recent) by calling `selectSprint(id)`
4. `selectSprint()` fetches `/api/sprints/:id/cards`, populates `state.cards`, calls `renderBoard()`

**Rendering:**

`renderBoard()` wipes `#board` and rebuilds the DOM from scratch each time. For each of the 6 statuses it creates a `.column` div, filters `state.cards` to that status, sorts by `position`, and appends a `.card` element per card via `buildCard()`.

`buildCard()` attaches drag event listeners and a click listener directly to the element. The card only shows the title and a priority dot — all other fields are in the modal.

**Drag and drop:**

Uses the native HTML5 Drag and Drop API — no library.

- `dragstart` on a `.card`: stores `card.id` in `dataTransfer` via `setData('card-id', id)`; applies `.dragging` class on next animation frame to avoid the ghost image being captured mid-fade
- `dragover` on a `.col-cards` zone: calls `preventDefault()` to signal the zone accepts drops; adds `.drag-over` highlight class
- `dragleave` on a `.col-cards` zone: only removes the highlight if `relatedTarget` is outside the zone (prevents flicker when moving over child elements)
- `drop` on a `.col-cards` zone: reads the card ID from `dataTransfer`, checks the card isn't already in that status, calls `updateCard(id, { ...card, status: newStatus })`, which PUTs to the server and re-renders

**Modals:**

Two modals share the same pattern: an overlay `div` is toggled via the `.hidden` class (which sets `display: none`). Clicking the overlay background, pressing `Escape`, or clicking Cancel closes them. Pressing `Enter` (outside a `<textarea>`) saves.

The card modal is dual-purpose: `state.editingCardId === null` means "create new", anything else means "edit existing". The Delete button is hidden (`visibility: hidden` to preserve layout) when creating.

**HTML escaping:**

User-supplied strings inserted into the DOM via `innerHTML` are passed through `esc()`, which escapes `&`, `<`, `>`, and `"` to prevent XSS.

---

## Statuses & Priorities

**Statuses** (column order):
1. Not Triaged
2. Backlog
3. In Progress
4. Needs Review
5. Ready Playback
6. Done

**Priorities** (indicated by colored dot on each card):
- Low — green
- Medium — amber
- High — red

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

`seed.py` populates the database with 3 sprints and 10 cards spread across statuses and priorities, useful for screenshots or testing. It is safe to re-run — sprints use `INSERT OR IGNORE` so they won't duplicate, though cards will be re-inserted each time. For a clean reset:

```bash
rm kanban.db && python3 seed.py
```

## Port

Pass an optional port as a positional argument:

```bash
python3 app.py           # binds to 8000
python3 app.py 9000      # binds to 9000
```

If the requested port is already in use, the server walks upward (`8001`, `8002`, …) until it finds a free one and prints the actual address it bound to.
