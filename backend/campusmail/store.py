"""Transactional, owner-scoped SQLite repository. No global student context."""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class NotFound(Exception): pass
class Conflict(Exception): pass


def now(): return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records(
                  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                  kind TEXT NOT NULL, source_key TEXT NOT NULL, payload TEXT NOT NULL,
                  revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  UNIQUE(owner_id, kind, source_key));
                CREATE INDEX IF NOT EXISTS owner_kind ON records(owner_id,kind);
                CREATE TABLE IF NOT EXISTS revisions(
                  record_id TEXT NOT NULL, owner_id TEXT NOT NULL, revision INTEGER NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id));
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    def create_user(self, name):
        if not name.strip(): raise ValueError('Profile name is required')
        user = {'id': uuid4().hex, 'name': name.strip()[:100], 'created_at': now()}
        with self.connect() as db:
            db.execute('INSERT INTO users VALUES(:id,:name,:created_at)', user)
        return user

    def users(self):
        with self.connect() as db: return [dict(x) for x in db.execute('SELECT * FROM users ORDER BY created_at')]

    def session(self, owner):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), owner))
        return token

    def owner_for_session(self, token):
        with self.connect() as db:
            row = db.execute('SELECT owner_id FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None: raise NotFound('Session not found')
        return row['owner_id']

    @staticmethod
    def decode(row):
        return {**json.loads(row['payload']), 'id': row['id'], 'owner_id': row['owner_id'],
                'kind': row['kind'], 'source_key': row['source_key'], 'revision': row['revision'],
                'created_at': row['created_at'], 'updated_at': row['updated_at']}

    def get(self, owner, record_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM records WHERE owner_id=? AND id=?', (owner, record_id)).fetchone()
        if row is None: raise NotFound('Record not found')
        return self.decode(row)

    def list(self, owner, kind=None):
        with self.connect() as db:
            query, args = 'SELECT * FROM records WHERE owner_id=?', [owner]
            if kind: query += ' AND kind=?'; args.append(kind)
            return [self.decode(x) for x in db.execute(query + ' ORDER BY created_at,id', args)]

    def put(self, owner, kind, payload, source_key=None, expected_revision=None):
        source_key = source_key or uuid4().hex
        clean = {k:v for k,v in payload.items() if k not in ('id','owner_id','kind','source_key','revision','created_at','updated_at')}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM records WHERE owner_id=? AND kind=? AND source_key=?', (owner,kind,source_key)).fetchone()
            if expected_revision is not None and (old is None or old['revision'] != expected_revision):
                raise Conflict('Record changed; refresh before approving')
            stamp = now()
            body = json.dumps(clean, ensure_ascii=False)
            if old:
                if old['payload'] == body: return self.decode(old)
                db.execute('INSERT INTO revisions VALUES(?,?,?,?,?)', (old['id'],owner,old['revision'],old['payload'],stamp))
                db.execute('UPDATE records SET payload=?,revision=revision+1,updated_at=? WHERE id=? AND owner_id=?', (body,stamp,old['id'],owner))
                record_id = old['id']
            else:
                record_id = uuid4().hex
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,1,?,?)', (record_id,owner,kind,source_key,body,stamp,stamp))
        return self.get(owner,record_id)

    def patch(self, owner, record_id, changes, expected_revision=None):
        record = self.get(owner,record_id)
        return self.put(owner,record['kind'],{**record,**changes},record['source_key'],
                        record['revision'] if expected_revision is None else expected_revision)

    def delete(self, owner, record_id):
        self.get(owner,record_id)
        with self.connect() as db:
            db.execute('DELETE FROM records WHERE owner_id=? AND id=?', (owner,record_id))

    def history(self, owner, record_id):
        self.get(owner,record_id)
        with self.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM revisions WHERE owner_id=? AND record_id=? ORDER BY revision',(owner,record_id))]
