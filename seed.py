import sqlite3
import os
from datetime import date, timedelta

DB = os.path.join(os.path.dirname(__file__), 'kanban.db')

def rel(days):
    return (date.today() + timedelta(days=days)).isoformat()

conn = sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys = ON')
conn.executescript('''
    CREATE TABLE IF NOT EXISTS sprints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS cards (
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
    CREATE TABLE IF NOT EXISTS card_dependencies (
        card_id    INTEGER NOT NULL,
        depends_on INTEGER NOT NULL,
        PRIMARY KEY (card_id, depends_on),
        FOREIGN KEY (card_id)    REFERENCES cards(id) ON DELETE CASCADE,
        FOREIGN KEY (depends_on) REFERENCES cards(id) ON DELETE CASCADE
    );
''')

# migrate existing DBs missing any column
for col in ('due_on TEXT', 'delivered_on TEXT', "notes TEXT NOT NULL DEFAULT ''"):
    try:
        conn.execute(f'ALTER TABLE cards ADD COLUMN {col}')
    except Exception:
        pass

# Wipe existing data so re-runs always produce fresh dates
conn.execute('DELETE FROM card_dependencies')
conn.execute('DELETE FROM cards')
conn.execute('DELETE FROM sprints')

conn.executemany('INSERT INTO sprints (id, name) VALUES (?,?)', [
    (1, 'Sprint 1 — Foundation'),
    (2, 'Sprint 2 — Core Features'),
    (3, 'Sprint 3 — Polish & Launch'),
])

# Cards — IDs are explicit so dependencies below can reference them reliably
# Due dates are relative to today so all cards appear in the Gantt window
# (sprint_id, title, description, status, priority, position, due_on, delivered_on, notes)
cards = [
    # ── Sprint 1 — Foundation ──
    (1, 1,  'Initialize repo and set up project structure',      '', 'Done',        'High',   1, rel(1),  rel(1),  ''),
    (2, 1,  'Configure database schema (projects, tasks, users)','', 'Done',        'High',   2, rel(2),  rel(2),  ''),
    (3, 1,  'Implement user authentication (sign up / login)',   '', 'In Progress', 'High',   1, rel(4),  None,    ''),
    (4, 1,  'Set up routing and navigation shell',               '', 'In Progress', 'Medium', 2, rel(4),  None,    ''),
    (5, 1,  'Deploy dev environment',                            '', 'Backlog',     'Medium', 1, rel(5),  None,    ''),

    # ── Sprint 2 — Core Features ──
    (6, 2,  'Create project CRUD (create, list, edit, delete)',  '', 'In Progress', 'High',   1, rel(9),  None,    ''),
    (7, 2,  'Create task CRUD within projects',                  '', 'Backlog',     'High',   1, rel(11), None,    ''),
    (8, 2,  'Build kanban board view for tasks',                 '', 'Backlog',     'High',   2, rel(12), None,    ''),
    (9, 2,  'Add task status updates (To Do / In Progress / Done)','','Backlog',    'Medium', 3, rel(12), None,    ''),
    (10, 2, 'Implement user assignment to tasks',                '', 'Backlog',     'Medium', 4, rel(15), None,    ''),
    (11, 2, 'Add due date and priority fields to tasks',         '', 'Backlog',     'Low',    5, rel(15), None,    ''),

    # ── Sprint 3 — Polish & Launch ──
    (12, 3, 'Build dashboard with project overview',             '', 'Backlog',     'High',   1, rel(17), None,    ''),
    (13, 3, 'Add search and filter for tasks',                   '', 'Backlog',     'Medium', 2, rel(19), None,    ''),
    (14, 3, 'Write unit tests for core flows',                   '', 'Backlog',     'Medium', 3, rel(21), None,    ''),
    (15, 3, 'UI/UX review and fixes',                            '', 'Backlog',     'Medium', 4, rel(23), None,    ''),
    (16, 3, 'Deploy to production',                              '', 'Backlog',     'High',   5, rel(25), None,    ''),
]

conn.executemany(
    '''INSERT INTO cards
       (id, sprint_id, title, description, status, priority, position, due_on, delivered_on, notes)
       VALUES (?,?,?,?,?,?,?,?,?,?)''',
    cards
)

# Dependencies — (card_id, depends_on)
# Read as: "card_id cannot start until depends_on is done"
dependencies = [
    (2,  1),   # Configure schema          → needs repo initialised
    (3,  2),   # User auth                 → needs schema configured
    (4,  1),   # Routing shell             → needs repo initialised
    (5,  3),   # Deploy dev env            → needs auth implemented
    (5,  4),   # Deploy dev env            → needs routing shell in place
    (6,  5),   # Project CRUD              → needs dev env deployed
    (7,  6),   # Task CRUD                 → needs project CRUD
    (8,  7),   # Kanban board view         → needs task CRUD
    (9,  8),   # Task status updates       → needs kanban board
    (10, 7),   # User assignment           → needs task CRUD
    (11, 7),   # Due date & priority fields→ needs task CRUD
    (12, 9),   # Dashboard                 → needs task status updates
    (12, 10),  # Dashboard                 → needs user assignment
    (12, 11),  # Dashboard                 → needs due date fields
    (13, 12),  # Search & filter           → needs dashboard
    (14, 12),  # Unit tests                → needs dashboard
    (15, 13),  # UI/UX review              → needs search & filter
    (16, 14),  # Deploy to production      → needs unit tests
    (16, 15),  # Deploy to production      → needs UI/UX sign-off
]

conn.executemany(
    'INSERT INTO card_dependencies (card_id, depends_on) VALUES (?,?)',
    dependencies
)

conn.commit()
conn.close()
print('Seeded: 3 sprints, 16 cards, 19 dependencies.')
