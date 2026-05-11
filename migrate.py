"""
Migration script — safe to run on any existing kanban.db regardless of age.
Applies all schema changes since the initial release in order, skipping any
that are already present. Running it multiple times is harmless.
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), 'kanban.db')


def column_exists(conn, table, column):
    rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    return any(r['name'] == column for r in rows)


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def run():
    if not os.path.exists(DB):
        print(f'No database found at {DB} — nothing to migrate.')
        print('Run `python3 app.py` once to create a fresh database.')
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')

    migrations = []

    # v1 → v2: timestamp fields
    if not column_exists(conn, 'cards', 'due_on'):
        conn.execute('ALTER TABLE cards ADD COLUMN due_on TEXT')
        migrations.append('cards.due_on')

    if not column_exists(conn, 'cards', 'delivered_on'):
        conn.execute('ALTER TABLE cards ADD COLUMN delivered_on TEXT')
        migrations.append('cards.delivered_on')

    # v2 → v3: notes field
    if not column_exists(conn, 'cards', 'notes'):
        conn.execute("ALTER TABLE cards ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        migrations.append('cards.notes')

    # v3 → v4: dependency tracking
    if not table_exists(conn, 'card_dependencies'):
        conn.execute('''
            CREATE TABLE card_dependencies (
                card_id    INTEGER NOT NULL,
                depends_on INTEGER NOT NULL,
                PRIMARY KEY (card_id, depends_on),
                FOREIGN KEY (card_id)    REFERENCES cards(id) ON DELETE CASCADE,
                FOREIGN KEY (depends_on) REFERENCES cards(id) ON DELETE CASCADE
            )
        ''')
        migrations.append('table card_dependencies')

    conn.commit()
    conn.close()

    if migrations:
        print('Migrations applied:')
        for m in migrations:
            print(f'  + {m}')
    else:
        print('Database is already up to date.')


if __name__ == '__main__':
    run()
