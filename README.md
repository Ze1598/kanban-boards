# Kanban Boards

A lightweight, local-first kanban board web app. No framework, no package manager, no build step. Runs entirely on Python's standard library with SQLite as the database.

---

## Requirements

- Python 3.8+

That's it — the web app has zero external dependencies.

The optional MCP server (`mcp_server.py`) additionally requires:

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — dependencies are declared inline via PEP 723 and installed automatically on first run

---

## Running

### Web app only

```bash
python3 app.py           # starts on port 8000
python3 app.py 9000      # starts on a specific port
```

Open the printed URL in your browser. The SQLite database (`kanban.db`) is created automatically on first run. If the requested port is already in use the server increments until it finds a free one and prints the actual URL.

To stop: `Ctrl+C`.

### Web app + MCP server

The MCP server is a separate process that proxies tool calls to the web app's HTTP API. Both must be running for agents to use the tools.

**Terminal 1** — web app:
```bash
python3 app.py 8000
```

**Terminal 2** — MCP server:
```bash
uv run mcp_server.py                              # connects to http://localhost:8000 (default)
KANBAN_URL=http://localhost:9000 uv run mcp_server.py  # if the web app is on a different port
```

`uv` installs the `mcp` dependency automatically on first run — no `pip install` or venv setup needed.

The MCP server communicates over stdio and is intended to be spawned by an MCP client (Claude Desktop, the `claude` CLI, etc.). Running it directly in a terminal is only useful for verifying it starts without error; it will sit silently waiting for JSON-RPC input.

---

## Project Structure

```
kanban-boards/
├── app.py              # HTTP server, request routing, all API handlers, DB init
├── mcp_server.py       # MCP server — exposes all API endpoints as agent-callable tools
├── test_mcp.py         # MCP smoke-test client (no browser required)
├── migrate.py          # Schema migration script — safe to run on any existing DB
├── seed.py             # Populates the DB with dummy sprints and cards for testing
├── kanban.db           # SQLite database (auto-created, not tracked in git)
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

**Sprints**

| Method   | Path                 | Body / notes                                       |
|----------|----------------------|----------------------------------------------------|
| `GET`    | `/api/sprints`       | List all sprints, ordered by `created_at DESC`     |
| `POST`   | `/api/sprints`       | `{ name }`                                         |
| `PUT`    | `/api/sprints/:id`   | `{ name }`                                         |
| `DELETE` | `/api/sprints/:id`   | Cascades to all cards in the sprint                |

**Cards**

| Method   | Path                       | Body / notes                                                                 |
|----------|----------------------------|------------------------------------------------------------------------------|
| `GET`    | `/api/sprints/:id/cards`   | Ordered by `position, id`                                                    |
| `POST`   | `/api/sprints/:id/cards`   | `{ title, description?, status?, priority?, due_on?, delivered_on?, notes? }` |
| `PUT`    | `/api/cards/:id`           | Any subset of card fields — missing fields retain their current values. Pass `sprint_id` to move a card to a different sprint. |
| `DELETE` | `/api/cards/:id`           | Removes all dependency rows involving this card                              |

**Dependencies**

| Method   | Path                                      | Body / notes                                              |
|----------|-------------------------------------------|-----------------------------------------------------------|
| `GET`    | `/api/sprints/:id/dependencies`           | Returns `[{ card_id, depends_on }]` for the sprint        |
| `GET`    | `/api/cards/:id/dependencies`             | Returns `{ predecessors: [{id, title}], successors: [{id, title}] }` |
| `POST`   | `/api/dependencies`                       | `{ card_id, depends_on }` — rejects self-loops and cycles (409) |
| `DELETE` | `/api/dependencies/:card_id/:depends_on`  | Removes a single dependency edge                          |

**Bulk operations**

All bulk endpoints accept up to 50 items per request and return a 413 if the limit is exceeded. The MCP server handles chunking automatically for larger sets.

| Method    | Path                        | Body / notes                                                                                   |
|-----------|-----------------------------|-----------------------------------------------------------------------------------------------|
| `PATCH`   | `/api/cards/bulk`           | `[{ id, ...fields }]` — updates each card, merging over existing values. Returns `{ updated: [...], errors: [{id, error}] }`. Failed items are reported in `errors`; the rest are still applied. |
| `POST`    | `/api/cards/bulk-move`      | `{ card_ids: [int], sprint_id }` — moves all listed cards to the target sprint. Returns `{ moved, requested }`. |
| `POST`    | `/api/dependencies/bulk`    | `[{ card_id, depends_on }]` — creates multiple dependency edges. Each edge is individually validated for self-loops and cycles; invalid ones go into `skipped` rather than aborting the batch. Returns `{ created, skipped: [{card_id, depends_on, reason}] }`. |

**Validation rules:**
- Status must be one of the eight canonical values; invalid values fall back to the existing value (on update) or `Not Triaged` (on create).
- Priority must be `Low`, `Medium`, or `High`; invalid values fall back similarly.
- Dates (`due_on`, `delivered_on`) are stored as ISO 8601 strings (`YYYY-MM-DD`) or `NULL`.

**Cycle detection:** Before inserting a dependency, the server runs a BFS from the proposed `depends_on` node following existing forward edges. If it can reach `card_id`, the new edge would form a cycle and the request is rejected with 409. In bulk mode the failing edge is skipped and the batch continues.

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

## MCP Server

`mcp_server.py` exposes the full API as [Model Context Protocol](https://modelcontextprotocol.io) tools, allowing AI agents (Claude Desktop, the `claude` CLI, or any MCP-compatible client) to read and write the board conversationally.

The MCP server is a **stdio server** — it is spawned as a subprocess by the MCP client and communicates over stdin/stdout. It does not listen on a port of its own. It proxies all tool calls to the kanban HTTP server, so that server must be running separately.

### Configuration

| Environment variable | Default                   | Purpose                                         |
|----------------------|---------------------------|-------------------------------------------------|
| `KANBAN_URL`         | `http://localhost:8000`   | Base URL of the running kanban server           |
| `KANBAN_BULK_CHUNK`  | `50`                      | Max items per backend call for bulk tools       |

### Claude Desktop setup

**1. Find the absolute paths you will need:**

```bash
which uv           # e.g. /Users/you/.local/bin/uv
pwd                # run from inside the kanban-boards directory
```

**2. Edit the Claude Desktop config file:**

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "kanban-boards": {
      "command": "/Users/you/.local/bin/uv",
      "args": ["run", "/Users/you/projects/kanban-boards/mcp_server.py"],
      "env": {
        "KANBAN_URL": "http://localhost:8000"
      }
    }
  }
}
```

**Both paths must be absolute.** Claude Desktop launches servers in a minimal environment that does not inherit your shell's `PATH`. If you write `"command": "uv"` it will fail with a connection error even though `uv` works fine in your terminal.

**3. Start the kanban server** (Claude Desktop will not start it for you):

```bash
python3 app.py 8000
```

**4. Fully quit and relaunch Claude Desktop** — Cmd+Q on macOS, not just closing the window.

**5. Verify the connection** — open a new conversation and look for the hammer icon near the message input. If it is missing, check the logs:

```bash
tail -f ~/Library/Logs/Claude/mcp*.log
```

The logs show the exact error. The two most common causes are a wrong path in the config (look for `No such file or directory`) and the kanban server not running (look for `Connection refused`).

### Available tools

**Sprint tools**

| Tool             | What it does                              |
|------------------|-------------------------------------------|
| `list_sprints`   | List all sprints                          |
| `create_sprint`  | Create a sprint                           |
| `update_sprint`  | Rename a sprint                           |
| `delete_sprint`  | Delete a sprint and all its cards         |

**Card tools**

| Tool           | What it does                                                            |
|----------------|-------------------------------------------------------------------------|
| `list_cards`   | List cards in a sprint                                                  |
| `create_card`  | Create a card (title, status, priority, due date, etc.)                 |
| `update_card`  | Update any card fields; pass `sprint_id` to move between sprints        |
| `delete_card`  | Delete a card                                                           |

**Dependency tools**

| Tool                       | What it does                                               |
|----------------------------|------------------------------------------------------------|
| `list_sprint_dependencies` | List all dependency edges in a sprint                      |
| `get_card_dependencies`    | Get predecessors and successors of a specific card         |
| `create_dependency`        | Create a dependency between two cards                      |
| `delete_dependency`        | Remove a dependency edge                                   |

**Bulk tools** — accept lists of any size; the server chunks automatically

| Tool                       | What it does                                                      |
|----------------------------|-------------------------------------------------------------------|
| `bulk_update_cards`        | Update multiple cards (e.g. set due dates, change status)         |
| `bulk_move_cards`          | Move multiple cards to a different sprint                         |
| `bulk_create_dependencies` | Create multiple dependency edges; cycles are skipped with reasons |

### Testing locally

#### Option A — programmatic smoke test (no browser, no npm)

`test_mcp.py` acts as an MCP client over stdio and exercises all major tool categories end-to-end: tool listing, sprint/card CRUD, bulk updates, and cycle detection.

Start the web app and seed the database first:

```bash
python3 app.py 8000
python3 seed.py
```

Then run the test, pointing it at whichever port the web app is on:

```bash
KANBAN_URL=http://localhost:8000 uv run test_mcp.py
```

`KANBAN_URL` must be set explicitly here because `test_mcp.py` spawns `mcp_server.py` as a subprocess and explicitly forwards the environment to it. Without it the subprocess falls back to `http://localhost:8000`, and if the web app shifted to another port (e.g. 8001 because 8000 was in use), every tool call fails silently with a connection error rather than a clear message.

**A note on FastMCP list serialisation:** tools that return a Python list (e.g. `list_sprints`, `list_cards`) produce one `TextContent` item per element in `result.content`, not a single JSON array blob. `test_mcp.py` accounts for this via `_parse_list()`. If you write your own MCP client against this server, use `[json.loads(item.text) for item in result.content]` for list-returning tools and `json.loads(result.content[0].text)` for tools that return a single object.

#### Option B — interactive browser inspector

```bash
uvx 'mcp[cli]' dev mcp_server.py
```

Opens a browser-based UI at `http://localhost:6274` where you can browse tool schemas and call them with custom inputs. The web app must be running separately.

**Important:** the command is `uvx 'mcp[cli]' dev`, not `uv run mcp dev`. The difference matters:

- `uv run mcp dev` — tells uv to run a script or command called `mcp`, which is not on the PATH, and fails with `Failed to spawn: mcp`.
- `uvx mcp dev` — finds the `mcp` CLI entry point but is missing the `typer` dependency, and fails with `typer is required. Install with 'pip install mcp[cli]'`.
- `uvx 'mcp[cli]' dev` — installs `mcp` with its CLI extras (including `typer`) and runs correctly.

The inspector's browser UI is powered by the `@modelcontextprotocol/inspector` npm package. On first run it will prompt `Ok to proceed? (y)` before downloading it. If you see an npm file conflict error, run `npm cache clean --force` and retry.

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
