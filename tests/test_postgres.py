"""PostgreSQL + pgvector integration tests (skipped without CAAS_DATABASE_URL)."""
from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("psycopg")

DSN = os.getenv("CAAS_DATABASE_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN or not DSN.startswith("postgres"),
    reason="Set CAAS_DATABASE_URL to a Postgres+pgvector instance",
)


@pytest.fixture()
def mem():
    from caas.embeddings import HashingEmbedder
    from caas.pgmemory import PostgresMemory
    from caas.postgres import connect

    # Isolate each test in its own tenant; truncate projections for cleanliness.
    m = PostgresMemory(DSN, embedder=HashingEmbedder(dim=384), auto_migrate=True)
    yield m
    m.close()


def _principal(tenant: str, subject: str, groups=()):
    from caas.multiscope import Principal

    return Principal(tenant, subject, frozenset(groups))


def test_write_search_and_vector_projection(mem):
    from caas.worker import process_batch

    tenant = "t-" + uuid.uuid4().hex[:8]
    a = _principal(tenant, "alice", ("eng",))
    mem.create_scope(a, "personal", "alice")
    mem.create_scope(a, "team", "eng")
    mem.grant(a, "team", "eng", "group:eng", "read")
    mem.grant(a, "team", "eng", "user:alice", "write")

    row = mem.write(
        a,
        "team",
        "eng",
        "Apollo launch window is Thursday for Platform review",
        "meeting",
    )
    assert process_batch(mem) >= 1

    lexical = mem.search(a, "Apollo", [("team", "eng")], mode="lexical")
    assert len(lexical["items"]) == 1

    vector = mem.search(a, "Apollo Thursday Platform", [("team", "eng")], mode="vector")
    assert any(i["id"] == row["id"] for i in vector["items"])

    hybrid = mem.search(a, "Apollo", [("team", "eng")], mode="hybrid")
    assert hybrid["manifest"][0]["id"] == row["id"]


def test_tenant_isolation_and_promotion_graph(mem):
    from caas.worker import process_batch

    tenant = "t-" + uuid.uuid4().hex[:8]
    other = "o-" + uuid.uuid4().hex[:8]
    a = _principal(tenant, "alice", ("eng",))
    b = _principal(tenant, "bob", ("eng",))
    outsider = _principal(other, "alice")

    mem.create_scope(a, "personal", "alice")
    mem.create_scope(a, "team", "eng")
    original = mem.write(a, "personal", "alice", "Apollo decision with Orion", "chat")
    assert mem.search(b, "Apollo", [("personal", "alice")])["items"] == []
    assert mem.search(outsider, "Apollo", [("personal", "alice")])["items"] == []

    mem.grant(a, "team", "eng", "group:eng", "read")
    mem.grant(a, "team", "eng", "user:alice", "write")
    promoted = mem.promote(a, original["id"], "team", "eng")
    assert promoted["id"] != original["id"]
    assert process_batch(mem) >= 1

    assert len(mem.search(b, "Apollo", [("team", "eng")])["items"]) == 1
    edges = mem.neighbors(a, promoted["id"], kind="memory")
    # derived_from should exist after worker projection
    assert any(e["relation"] == "derived_from" for e in edges)


def test_explicit_relate_and_revise(mem):
    from caas.multiscope import Conflict
    from caas.worker import process_batch

    tenant = "t-" + uuid.uuid4().hex[:8]
    a = _principal(tenant, "a")
    mem.create_scope(a, "personal", "a")
    r = mem.write(a, "personal", "a", "Orion depends on Apollo", "chat")
    process_batch(mem)
    edge = mem.relate(a, "Orion", "depends_on", "Apollo", memory_id=r["id"])
    assert edge["relation"] == "depends_on"
    assert mem.neighbors(a, "Orion", relation="depends_on")

    assert mem.revise(a, r["id"], "new", 1)["version"] == 2
    with pytest.raises(Conflict):
        mem.revise(a, r["id"], "stale", 1)
    mem.revise(a, r["id"], "", 2, delete=True)
    process_batch(mem)
    assert mem.search(a, "new", [("personal", "a")])["items"] == []
