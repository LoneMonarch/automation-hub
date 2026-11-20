"""Durable queue. Original inputs are never modified."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def data_dir():
    if os.environ.get('AUTOMATION_HUB_DATA'):
        return Path(os.environ['AUTOMATION_HUB_DATA'])
    if sys.platform == 'win32':
        return Path(os.environ['LOCALAPPDATA']) / 'AutomationHub'
    return Path.home() / 'Library' / 'Application Support' / 'AutomationHub'


def digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


class Store:
    def __init__(self, root=None):
        self.root = Path(root or data_dir())
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'hub.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, module TEXT NOT NULL, original TEXT, path TEXT,
          fingerprint TEXT, scope TEXT, settings TEXT, state TEXT, name TEXT,
          attempts INTEGER DEFAULT 0, baseline TEXT, remote_id TEXT,
          verification TEXT, error TEXT, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS events (job TEXT, state TEXT, detail TEXT, at TEXT);
        CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS historical (source TEXT PRIMARY KEY, content TEXT, imported TEXT);
        ''')
        self.db.commit()

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, json.dumps(value)))

    def rows(self, module=None):
        query = 'SELECT * FROM jobs'
        args = ()
        if module:
            query += ' WHERE module=?'
            args = (module,)
        return [dict(r) for r in self.db.execute(query + ' ORDER BY created', args)]

    def job(self, ident):
        return dict(self.db.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone())

    def enqueue(self, module, files, settings, again=False):
        scope = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        added = skipped = 0
        for source in files:
            source = Path(source).resolve()
            fingerprint = digest(source)
            existing = self.db.execute("SELECT 1 FROM jobs WHERE module=? AND fingerprint=? AND scope=? AND state NOT IN ('failed','cancelled')", (module, fingerprint, scope)).fetchone()
            if existing and not again:
                skipped += 1
                continue
            ident = uuid.uuid4().hex
            folder = self.root / 'queue' / ident
            folder.mkdir(parents=True)
            target = folder / source.name
            shutil.copy2(source, target)
            if digest(target) != fingerprint:
                raise ValueError('File changed while being copied. Select it again.')
            with self.db:
                self.db.execute('''INSERT INTO jobs
                (id,module,original,path,fingerprint,scope,settings,state,created,updated)
                VALUES (?,?,?,?,?,?,?,'queued',?,?)''', (ident,module,str(source),str(target),fingerprint,scope,json.dumps(settings),now(),now()))
            added += 1
        return added, skipped

    def transition(self, ident, state, **fields):
        allowed = {'name','attempts','baseline','remote_id','verification','error'}
        if set(fields) - allowed:
            raise ValueError('Unsupported job fields')
        fields.update(state=state, updated=now())
        with self.db:
            self.db.execute('UPDATE jobs SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', (*fields.values(),ident))
            self.db.execute('INSERT INTO events VALUES (?,?,?,?)', (ident,state,fields.get('error',''),now()))

    def export(self, path):
        rows = self.rows()
        fields = ['id','module','original','state','name','attempts','remote_id','verification','error','created','updated']
        with open(path,'w',newline='',encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
            writer.writeheader()
            # Prevent spreadsheet formula evaluation in reports.
            writer.writerows({k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in r.items()} for r in rows)


class QueueLock:
    """OS-held lock; automatically released if the worker crashes."""
    def __init__(self, root):
        self.path = Path(root) / 'worker.lock'

    def __enter__(self):
        self.file = open(self.path,'a+b')
        self.file.seek(0)
        self.file.write(b'0')
        self.file.flush()
        self.file.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('Another job is already running. Wait for it to finish.')
        return self

    def __exit__(self,*args):
        self.file.close()
