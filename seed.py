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
    (1, 'Sprint 11'),
    (2, 'Sprint 12'),
    (3, 'Sprint 13'),
])

# Cards — IDs are explicit so dependencies below can reference them reliably
# (sprint_id, title, description, status, priority, position, due_on, delivered_on, notes)
cards = [
    # ── Sprint 11 ── (completed, wrapped up ~2-3 weeks ago)
    (1, 1,  'Define component library tokens',    'Establish spacing, colour, and typography tokens in a shared config file.',                          'Done',          'High',   1, rel(-20), rel(-21), ''),
    (2, 1,  'Redesign user profile page',          'Update layout to match the new token-based design system. Needs mobile breakpoints.',                'Done',          'High',   2, rel(-14), rel(-15), 'Merged. Minor spacing tweak requested by design post-review — deferred to Sprint 12.'),
    (3, 1,  'Add loading skeleton to dashboard',   'Replace spinner with skeleton screens for the three main widgets.',                                  'Done',          'Medium', 3, rel(-14), rel(-13), 'Delivered one day late due to a Safari CSS bug. Fix was a fallback animation via keyframes.'),
    (4, 1,  'Fix broken pagination on feed',       'Items 21–30 return a 500. Likely an off-by-one in the SQL offset.',                                 'Done',          'High',   4, rel(-14), rel(-14), ''),
    (5, 1,  'Audit npm dependencies for CVEs',     '',                                                                                                  'Needs Review',  'Low',    1, rel(-7),  None,      'Found 2 moderate CVEs in dev dependencies only. Not exploitable in prod. Awaiting sign-off.'),

    # ── Sprint 12 ── (active, mid-sprint)
    (6, 2,  'Harden CSP headers',                  'Set Content-Security-Policy, X-Frame-Options, and Referrer-Policy on all responses.',                'Done',          'High',   1, rel(-7),  rel(-8),  ''),
    (7, 2,  'Migrate auth tokens to httpOnly cookies', 'Current localStorage approach flagged in security review. Depends on CSP being locked down first. See ticket SEC-88.', 'In Progress', 'High', 2, rel(-1),  None, 'Blocked on backend cookie domain config. Need to align with infra on sameSite policy before proceeding.'),
    (8, 2,  'Write auth integration tests',         'Cover login, logout, and token refresh flows against the new httpOnly cookie implementation.',      'Backlog',       'High',   3, rel(5),   None,      ''),
    (9, 2,  'Build sprint reporting view',          'Bar chart of cards by status per sprint. Use canvas, no chart lib.',                                'In Progress',   'Medium', 1, rel(-1),  None,      ''),
    (10, 2, 'Dark mode support',                    'Respect prefers-color-scheme. CSS custom properties are already in place — needs a theme toggle too.', 'Not Triaged', 'Low',  1, None,      None,      ''),

    # ── Sprint 13 ── (planned, starting next week)
    (11, 3, 'Public API v1 spec',                   'Write OpenAPI spec for the first public-facing endpoints. Auth and cards only for v1.',             'Backlog',       'High',   1, rel(10),  None,      ''),
    (12, 3, 'Rate limiting middleware',              'Add per-IP rate limiting to all /api/* routes. Depends on CSP and auth work being stable.',        'Backlog',       'High',   2, rel(10),  None,      ''),
    (13, 3, 'Export board to CSV',                  'Allow exporting all cards for a sprint as a CSV download from the reporting view.',                 'Backlog',       'Low',    1, rel(17),  None,      ''),
    (14, 3, 'End-to-end test suite',                'Playwright tests covering the golden path: create sprint, add cards, drag across columns.',         'Not Triaged',   'Medium', 1, None,      None,      ''),
]

conn.executemany(
    '''INSERT INTO cards
       (id, sprint_id, title, description, status, priority, position, due_on, delivered_on, notes)
       VALUES (?,?,?,?,?,?,?,?,?,?)''',
    cards
)

# Dependencies — (card_id depends_on predecessor_id)
# Read as: "card_id cannot start until depends_on is done"
dependencies = [
    (2,  1),   # Redesign profile page        → needs component tokens first
    (3,  2),   # Loading skeleton              → needs redesigned profile page
    (7,  6),   # Migrate auth to httpOnly      → needs CSP headers hardened
    (8,  7),   # Auth integration tests        → needs httpOnly migration done
    (12, 7),   # Rate limiting middleware       → needs auth migration stable
    (12, 6),   # Rate limiting middleware       → also needs CSP hardened
    (11, 8),   # Public API v1 spec            → needs auth tests passing
    (13, 9),   # Export to CSV                 → needs reporting view built
    (14, 8),   # E2E test suite                → needs auth integration tests
    (14, 13),  # E2E test suite                → needs CSV export to exist
]

conn.executemany(
    'INSERT INTO card_dependencies (card_id, depends_on) VALUES (?,?)',
    dependencies
)

conn.commit()
conn.close()
print('Seeded: 3 sprints, 14 cards, 10 dependencies.')
