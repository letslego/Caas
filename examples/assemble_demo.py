#!/usr/bin/env python3
"""Assemble demo: working + profile + durable + episodes + knowledge under NFR budgets."""
from __future__ import annotations

from caas import Principal, open_context


def main() -> None:
    import uuid

    svc = open_context()
    # Prefer ephemeral SQLite for the demo unless caller exports CAAS_DATABASE_URL.
    p = Principal("acme", "alice", frozenset({"platform"}))
    team = "platform-" + uuid.uuid4().hex[:6]

    def ensure(kind, sid, classification="internal"):
        try:
            svc.memory.create_scope(p, kind, sid, classification)
        except Exception:
            if hasattr(svc.memory, "conn"):
                try:
                    svc.memory.conn.rollback()
                except Exception:
                    pass

    ensure("personal", "alice")
    ensure("team", team)
    try:
        svc.memory.grant(p, "team", team, "group:platform", "read")
        svc.memory.grant(p, "team", team, "user:alice", "write")
    except Exception:
        if hasattr(svc.memory, "conn"):
            try:
                svc.memory.conn.rollback()
            except Exception:
                pass

    svc.set_profile_fact(p, "verbosity", "concise")
    svc.set_profile_fact(p, "expertise", "advanced")
    svc.append_turn(p, "demo", "user", "Remind me what we decided for Orion storage.")
    svc.memory.write(
        p,
        "team",
        team,
        "Architecture decision: Orion uses Postgres + pgvector for CaaS.",
        "design-review",
        memory_type="decision",
    )
    svc.record_episode(p, "decision", "Orion storage", "Postgres + pgvector approved")
    svc.ingest_document(
        p,
        "CaaS NFR brief",
        "Working memory is hot and ephemeral. Durable scoped memory is the system of record. "
        "Kill switches fail closed on writes. Assemble packs planes under a character budget.",
        "architecture",
    )

    pack = svc.assemble(
        p,
        "demo",
        "Orion Postgres working durable",
        [("personal", "alice"), ("team", team)],
        max_chars=3500,
        include_operational=True,
    )
    print("timings_ms:", pack["timings_ms"])
    print("planes:", [s["plane"] for s in pack["sections"]])
    print("--- prompt ---")
    print(pack["prompt"][:1200])
    print("--- manifest entries ---", len(pack["manifest"]))


if __name__ == "__main__":
    main()
