import sqlite3

DB = 'kanban.db'

conn = sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys = ON')
conn.executescript('''
    CREATE TABLE IF NOT EXISTS sprints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sprint_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Not Triaged',
        priority TEXT NOT NULL DEFAULT 'Medium',
        position INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        due_on TEXT,
        delivered_on TEXT,
        notes TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (sprint_id) REFERENCES sprints(id) ON DELETE CASCADE
    );
''')

# migrate existing DBs that predate these columns
for col in ('due_on TEXT', 'delivered_on TEXT', "notes TEXT NOT NULL DEFAULT ''"):
    try:
        conn.execute(f'ALTER TABLE cards ADD COLUMN {col}')
    except sqlite3.OperationalError:
        pass

conn.executemany('INSERT OR IGNORE INTO sprints (id, name) VALUES (?,?)', [
    (1, 'Sprint 11'),
    (2, 'Sprint 12'),
    (3, 'Sprint 13'),
])

conn.executemany(
    '''INSERT INTO cards
       (sprint_id, title, description, status, priority, position, due_on, delivered_on, notes)
       VALUES (?,?,?,?,?,?,?,?,?)''',
    [
        # Sprint 11 — mostly done
        (1, 'Redesign user profile page',        'Update layout to match new design system. Needs mobile breakpoints.', 'Done',          'High',   1, '2026-03-14', '2026-03-13', 'Merged. Minor spacing tweak requested by design post-review — deferred to Sprint 12.'),
        (1, 'Fix broken pagination on feed',     'Items 21–30 return a 500. Likely an off-by-one in the SQL offset.',  'Done',          'High',   2, '2026-03-14', '2026-03-14', ''),
        (1, 'Add loading skeleton to dashboard', 'Replace spinner with skeleton screens for the three main widgets.',  'Done',          'Medium', 3, '2026-03-14', '2026-03-15', 'Delivered one day late due to Safari CSS bug. Fix was a fallback animation via keyframes.'),
        (1, 'Audit npm dependencies for CVEs',   '',                                                                    'Needs Review',  'Low',    1, '2026-03-21', None,          'Found 2 moderate CVEs in dev dependencies only. Not exploitable in prod. Awaiting sign-off.'),

        # Sprint 12 — active sprint
        (2, 'Migrate auth tokens to httpOnly cookies', 'Current localStorage approach flagged in security review. See ticket SEC-88.', 'In Progress', 'High',   1, '2026-04-25', None, 'Blocked on backend cookie domain config. Need to align with infra on sameSite policy before proceeding.'),
        (2, 'Build sprint reporting view',             'Bar chart of cards by status per sprint. Use canvas, no chart lib.',            'In Progress', 'Medium', 2, '2026-04-25', None, ''),
        (2, 'Write API integration tests',             'Cover all /api/cards endpoints. Use Python unittest + http.client.',            'Backlog',     'Medium', 1, '2026-04-25', None, ''),
        (2, 'Dark mode support',                       'Respect prefers-color-scheme. CSS custom properties are already in place.',     'Not Triaged', 'Low',    1, None,         None, ''),

        # Sprint 13 — future sprint
        (3, 'Export board to CSV',  'Allow exporting all cards for a sprint as a CSV download.',      'Backlog',     'Low',    1, '2026-05-09', None, ''),
        (3, 'Card due dates',       'Add optional due_date field and highlight overdue cards in red.', 'Not Triaged', 'Medium', 1, None,         None, ''),
    ]
)

conn.commit()
conn.close()
print('Seeded: 3 sprints, 10 cards.')
