"""Working / profile / episodic / knowledge / assemble / ops planes."""
from __future__ import annotations

import uuid

import pytest

from caas.context_service import ContextService
from caas.multiscope import Denied, Principal
from caas.working import WorkingMemory


def test_working_cas_and_bounds():
    wm = WorkingMemory(ttl_sec=60, max_turns=3, max_chars=1000)
    s = wm.append("t", "a", "s1", "user", "one")
    assert s.revision == 1
    s = wm.append("t", "a", "s1", "assistant", "two")
    s = wm.append("t", "a", "s1", "user", "three")
    s = wm.append("t", "a", "s1", "user", "four")
    assert len(s.turns) == 3
    assert s.turns[0].content == "two"


def test_context_service_planes_sqlite():
    from caas.multiscope import Memory

    mem = Memory(":memory:")
    svc = ContextService(mem)
    p = Principal("acme", "alice", frozenset({"platform"}))
    mem.create_scope(p, "personal", "alice")
    mem.write(p, "personal", "alice", "Orion uses Postgres", "chat")

    svc.set_profile_fact(p, "verbosity", "concise")
    assert svc.get_profile(p)["facts"]["verbosity"]["value"] == "concise"

    svc.append_turn(p, "sess-1", "user", "What DB did we pick?")
    svc.record_episode(p, "decision", "Chose Postgres", "For CaaS durable store")
    doc = svc.ingest_document(
        p,
        "Runbook",
        "Orion durable memory uses PostgreSQL with pgvector embeddings.",
        "wiki",
    )
    assert doc["chunks"] >= 1

    pack = svc.assemble(
        p,
        "sess-1",
        "Postgres Orion",
        [("personal", "alice")],
        max_chars=4000,
        include_operational=True,
    )
    assert "Working" in pack["prompt"] or "working" in str(pack["sections"]).lower()
    assert pack["timings_ms"]["total_ms"] >= 0
    planes = {s["plane"] for s in pack["sections"]}
    assert "durable" in planes or "knowledge" in planes or "profile" in planes

    svc.set_caps(p, max_steps=2)
    svc.record_usage(p, steps=1)
    with pytest.raises(Denied):
        svc.record_usage(p, steps=5)

    svc.set_kill_switch(p, True, "maintenance")
    with pytest.raises(Denied):
        svc.append_turn(p, "sess-1", "user", "blocked")
    svc.set_kill_switch(p, False, "ok")


@pytest.mark.skipif(
    not __import__("os").getenv("CAAS_DATABASE_URL", "").startswith("postgres"),
    reason="Postgres optional",
)
def test_context_service_postgres():
    from caas.pgmemory import PostgresMemory

    mem = PostgresMemory(__import__("os").environ["CAAS_DATABASE_URL"])
    svc = ContextService(mem)
    p = Principal("t-" + uuid.uuid4().hex[:8], "alice")
    mem.create_scope(p, "personal", "alice")
    svc.set_profile_fact(p, "expertise", "advanced")
    svc.ingest_document(p, "Doc", "pgvector cosine search for Orion", "doc")
    pack = svc.assemble(p, "s", "Orion pgvector", [("personal", "alice")])
    assert isinstance(pack["prompt"], str)
    mem.close()
