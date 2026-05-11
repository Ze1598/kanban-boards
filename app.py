import argparse
import http.server
import json
import socket
import sqlite3
import os
import re
from urllib.parse import urlparse

DB_PATH = os.path.join(os.path.dirname(__file__), 'kanban.db')
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

STATUSES = ['Not Triaged', 'Backlog', 'Blocked', 'In Progress', 'Needs Review', 'Ready Playback', 'On Standby', 'Done']


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_db()
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
    conn.commit()
    conn.close()


class KanbanHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress noisy request logging

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def serve_static(self, path):
        if path == '/':
            path = '/index.html'
        file_path = os.path.join(STATIC_DIR, path.lstrip('/'))
        # prevent path traversal
        if not os.path.abspath(file_path).startswith(os.path.abspath(STATIC_DIR)):
            self.send_response(403)
            self.end_headers()
            return
        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            return
        ext = os.path.splitext(file_path)[1]
        types = {'.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript'}
        with open(file_path, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', types.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/sprints':
            self.handle_get_sprints()
        elif m := re.match(r'^/api/sprints/(\d+)/cards$', path):
            self.handle_get_cards(int(m.group(1)))
        elif m := re.match(r'^/api/sprints/(\d+)/dependencies$', path):
            self.handle_get_dependencies(int(m.group(1)))
        elif m := re.match(r'^/api/cards/(\d+)/dependencies$', path):
            self.handle_get_card_dependencies(int(m.group(1)))
        else:
            self.serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/sprints':
            self.handle_create_sprint()
        elif m := re.match(r'^/api/sprints/(\d+)/cards$', path):
            self.handle_create_card(int(m.group(1)))
        elif path == '/api/dependencies':
            self.handle_create_dependency()
        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if m := re.match(r'^/api/sprints/(\d+)$', path):
            self.handle_update_sprint(int(m.group(1)))
        elif m := re.match(r'^/api/cards/(\d+)$', path):
            self.handle_update_card(int(m.group(1)))
        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if m := re.match(r'^/api/sprints/(\d+)$', path):
            self.handle_delete_sprint(int(m.group(1)))
        elif m := re.match(r'^/api/cards/(\d+)$', path):
            self.handle_delete_card(int(m.group(1)))
        elif m := re.match(r'^/api/dependencies/(\d+)/(\d+)$', path):
            self.handle_delete_dependency(int(m.group(1)), int(m.group(2)))
        else:
            self.send_json({'error': 'Not found'}, 404)

    # --- Sprint handlers ---

    def handle_get_sprints(self):
        conn = get_db()
        rows = [dict(r) for r in conn.execute('SELECT * FROM sprints ORDER BY created_at DESC')]
        conn.close()
        self.send_json(rows)

    def handle_create_sprint(self):
        data = self.read_json()
        name = data.get('name', '').strip()
        if not name:
            self.send_json({'error': 'Name required'}, 400)
            return
        conn = get_db()
        cur = conn.execute('INSERT INTO sprints (name) VALUES (?)', (name,))
        conn.commit()
        row = dict(conn.execute('SELECT * FROM sprints WHERE id = ?', (cur.lastrowid,)).fetchone())
        conn.close()
        self.send_json(row, 201)

    def handle_update_sprint(self, sprint_id):
        data = self.read_json()
        name = data.get('name', '').strip()
        if not name:
            self.send_json({'error': 'Name required'}, 400)
            return
        conn = get_db()
        conn.execute('UPDATE sprints SET name = ? WHERE id = ?', (name, sprint_id))
        conn.commit()
        row = conn.execute('SELECT * FROM sprints WHERE id = ?', (sprint_id,)).fetchone()
        conn.close()
        self.send_json(dict(row) if row else {'error': 'Not found'}, 200 if row else 404)

    def handle_delete_sprint(self, sprint_id):
        conn = get_db()
        conn.execute('DELETE FROM sprints WHERE id = ?', (sprint_id,))
        conn.commit()
        conn.close()
        self.send_json({'ok': True})

    def _has_path(self, conn, from_id, to_id):
        """BFS: does a dependency path already exist from from_id to to_id?"""
        visited, queue = set(), [from_id]
        while queue:
            node = queue.pop(0)
            if node == to_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            rows = conn.execute(
                'SELECT depends_on FROM card_dependencies WHERE card_id=?', (node,)
            ).fetchall()
            queue.extend(r[0] for r in rows)
        return False

    def handle_create_dependency(self):
        data = self.read_json()
        card_id   = data.get('card_id')
        depends_on = data.get('depends_on')
        if not card_id or not depends_on:
            self.send_json({'error': 'card_id and depends_on required'}, 400)
            return
        if card_id == depends_on:
            self.send_json({'error': 'A card cannot depend on itself'}, 400)
            return
        conn = get_db()
        # cycle check: would adding (card_id → depends_on) create a cycle?
        # a cycle exists if depends_on already (transitively) depends on card_id
        if self._has_path(conn, depends_on, card_id):
            conn.close()
            self.send_json({'error': 'This dependency would create a cycle'}, 409)
            return
        conn.execute(
            'INSERT OR IGNORE INTO card_dependencies (card_id, depends_on) VALUES (?,?)',
            (card_id, depends_on)
        )
        conn.commit()
        conn.close()
        self.send_json({'ok': True}, 201)

    def handle_delete_dependency(self, card_id, depends_on):
        conn = get_db()
        conn.execute(
            'DELETE FROM card_dependencies WHERE card_id=? AND depends_on=?',
            (card_id, depends_on)
        )
        conn.commit()
        conn.close()
        self.send_json({'ok': True})

    def handle_get_card_dependencies(self, card_id):
        conn = get_db()
        predecessors = [dict(r) for r in conn.execute('''
            SELECT c.id, c.title FROM card_dependencies d
            JOIN cards c ON c.id = d.depends_on
            WHERE d.card_id = ?
        ''', (card_id,))]
        successors = [dict(r) for r in conn.execute('''
            SELECT c.id, c.title FROM card_dependencies d
            JOIN cards c ON c.id = d.card_id
            WHERE d.depends_on = ?
        ''', (card_id,))]
        conn.close()
        self.send_json({'predecessors': predecessors, 'successors': successors})

    def handle_get_dependencies(self, sprint_id):
        conn = get_db()
        rows = [dict(r) for r in conn.execute('''
            SELECT d.card_id, d.depends_on
            FROM card_dependencies d
            JOIN cards c ON c.id = d.card_id
            WHERE c.sprint_id = ?
        ''', (sprint_id,))]
        conn.close()
        self.send_json(rows)

    # --- Card handlers ---

    def handle_get_cards(self, sprint_id):
        conn = get_db()
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM cards WHERE sprint_id = ? ORDER BY position, id', (sprint_id,)
        )]
        conn.close()
        self.send_json(rows)

    def handle_create_card(self, sprint_id):
        data = self.read_json()
        title = data.get('title', '').strip()
        if not title:
            self.send_json({'error': 'Title required'}, 400)
            return
        status = data.get('status', 'Not Triaged')
        if status not in STATUSES:
            status = 'Not Triaged'
        priority = data.get('priority', 'Medium')
        if priority not in ('Low', 'Medium', 'High'):
            priority = 'Medium'
        description = data.get('description', '')
        due_on = data.get('due_on') or None
        delivered_on = data.get('delivered_on') or None
        notes = data.get('notes', '')
        conn = get_db()
        max_pos = conn.execute(
            'SELECT COALESCE(MAX(position), 0) FROM cards WHERE sprint_id = ? AND status = ?',
            (sprint_id, status)
        ).fetchone()[0]
        cur = conn.execute(
            'INSERT INTO cards (sprint_id, title, description, status, priority, position, due_on, delivered_on, notes) VALUES (?,?,?,?,?,?,?,?,?)',
            (sprint_id, title, description, status, priority, max_pos + 1, due_on, delivered_on, notes)
        )
        conn.commit()
        row = dict(conn.execute('SELECT * FROM cards WHERE id = ?', (cur.lastrowid,)).fetchone())
        conn.close()
        self.send_json(row, 201)

    def handle_update_card(self, card_id):
        data = self.read_json()
        conn = get_db()
        existing = conn.execute('SELECT * FROM cards WHERE id = ?', (card_id,)).fetchone()
        if not existing:
            conn.close()
            self.send_json({'error': 'Not found'}, 404)
            return
        existing = dict(existing)
        title = data.get('title', existing['title']).strip() or existing['title']
        description = data.get('description', existing['description'])
        status = data.get('status', existing['status'])
        if status not in STATUSES:
            status = existing['status']
        priority = data.get('priority', existing['priority'])
        if priority not in ('Low', 'Medium', 'High'):
            priority = existing['priority']
        position = data.get('position', existing['position'])
        due_on = data.get('due_on', existing['due_on']) or None
        delivered_on = data.get('delivered_on', existing['delivered_on']) or None
        notes = data.get('notes', existing['notes'])
        conn.execute(
            'UPDATE cards SET title=?, description=?, status=?, priority=?, position=?, due_on=?, delivered_on=?, notes=? WHERE id=?',
            (title, description, status, priority, position, due_on, delivered_on, notes, card_id)
        )
        conn.commit()
        row = dict(conn.execute('SELECT * FROM cards WHERE id = ?', (card_id,)).fetchone())
        conn.close()
        self.send_json(row)

    def handle_delete_card(self, card_id):
        conn = get_db()
        conn.execute('DELETE FROM cards WHERE id = ?', (card_id,))
        conn.commit()
        conn.close()
        self.send_json({'ok': True})


def find_open_port(start):
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                port += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Kanban board server')
    parser.add_argument('port', nargs='?', type=int, default=8000,
                        help='port to listen on (default: 8000)')
    args = parser.parse_args()

    port = find_open_port(args.port)
    if port != args.port:
        print(f'Port {args.port} in use, using {port} instead.')

    init_db()
    server = http.server.HTTPServer(('localhost', port), KanbanHandler)
    print(f'Kanban board → http://localhost:{port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
