"""Local Postgres+pgvector demo. Requires CAAS_DATABASE_URL."""
from __future__ import annotations

import os
import sys

from caas.embeddings import HashingEmbedder
from caas.multiscope import Principal
from caas.pgmemory import PostgresMemory
from caas.worker import process_batch

url = os.getenv("CAAS_DATABASE_URL") or os.getenv("DATABASE_URL")
if not url:
    print("Set CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas", file=sys.stderr)
    sys.exit(1)

db = PostgresMemory(url, embedder=HashingEmbedder())
alice = Principal("acme", "alice", frozenset({"platform"}))
bob = Principal("acme", "bob", frozenset({"platform"}))

import uuid

from psycopg.errors import UniqueViolation

team = "platform-" + uuid.uuid4().hex[:6]
try:
    db.create_scope(alice, "personal", "alice")
except UniqueViolation:
    db.conn.rollback()
db.create_scope(alice, "team", team)
db.grant(alice, "team", team, "group:platform", "read")
db.grant(alice, "team", team, "user:alice", "write")

private = db.write(alice, "personal", "alice", "Prefers short design reviews", "conversation")
shared = db.write(
    alice,
    "team",
    team,
    "Architecture review is on Thursdays for Apollo",
    "meeting",
)
print("outbox processed", process_batch(db))

assert db.search(bob, "reviews", [("personal", "alice")])["items"] == []
print("bob sees:", db.search(bob, "Thursday Apollo", [("team", team)], mode="hybrid")["context"])
db.relate(alice, "Apollo", "scheduled_on", "Thursdays")
print("neighbors:", db.neighbors(alice, "Apollo", direction="out"))
print("path:", db.path(alice, "Apollo", "Thursdays"))
print("history versions:", len(db.history(alice, label="Apollo")))
db.close()
