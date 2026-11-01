"""SQLite durable adapter for local development only."""
import sqlite3
from dataclasses import asdict
from datetime import datetime
from .core import ContextItem

class SQLiteStore:
    def __init__(self, path='caas.db'):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS memory (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, scope TEXT NOT NULL, owner TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, classification TEXT NOT NULL, version INTEGER NOT NULL, timestamp TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_memory_tenant ON memory(tenant)')
        self.db.commit()
    def put(self, item: ContextItem):
        d=asdict(item); d['timestamp']=item.timestamp.isoformat()
        self.db.execute('INSERT INTO memory VALUES (:id,:tenant,:scope,:owner,:text,:source,:classification,:version,:timestamp) ON CONFLICT(id) DO UPDATE SET text=excluded.text, version=excluded.version, timestamp=excluded.timestamp',d)
        self.db.commit()
    def search(self, tenant: str, query: str):
        words=[w.lower() for w in query.split() if w.strip()]
        if not words: return []
        rows=self.db.execute('SELECT * FROM memory WHERE tenant=? ORDER BY timestamp DESC LIMIT 1000',(tenant,)).fetchall()
        return [ContextItem(*r[:8],datetime.fromisoformat(r[8])) for r in rows if any(w in r[4].lower() for w in words)]
