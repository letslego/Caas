#!/usr/bin/env python3
"""Team assistant: shared team memory with explicit grants.

Owner creates the team scope, grants group:platform read (and optional write),
then teammates retrieve shared decisions. Non-members remain denied.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    backend,
    deny,
    ensure_scope,
    maybe_drain,
    principal,
    read,
    section,
    show_retrieve,
    write,
)


def main() -> None:
    db = backend()
    alice = principal("acme", "alice", "platform")  # owner + member
    bob = principal("acme", "bob", "platform")  # teammate
    cara = principal("acme", "cara", "sales")  # different group

    team = "platform-" + uuid.uuid4().hex[:6]

    section("Setup team scope + grants")
    ensure_scope(db, alice, "team", team)
    db.grant(alice, "team", team, "group:platform", "read")
    db.grant(alice, "team", team, "user:alice", "write")
    # Optional: allow bob to write shared notes
    db.grant(alice, "team", team, "user:bob", "write")
    print("grants: group:platform=read, user:alice=write, user:bob=write")

    section("WRITE — team decisions and schedule")
    decision = write(
        db,
        alice,
        "team",
        team,
        "Architecture decision: Orion will use Postgres + pgvector for CaaS memory; no separate graph DB in v0.5.",
        "design-review",
        memory_type="decision",
    )
    schedule = write(
        db,
        bob,
        "team",
        team,
        "Platform review is Thursdays 10:00 America/New_York; agenda owners rotate weekly.",
        "meeting",
        memory_type="fact",
    )
    print("wrote", decision["id"], "and", schedule["id"])
    maybe_drain(db)

    if hasattr(db, "relate"):
        section("GRAPH — assert typed team knowledge")
        db.relate(alice, "Orion", "uses", "Postgres", memory_id=decision["id"])
        db.relate(alice, "Orion", "uses", "pgvector", memory_id=decision["id"])
        print("neighbors(Orion):", db.neighbors(alice, "Orion", direction="out"))

    section("READ — teammates retrieve shared context")
    show_retrieve(
        "bob asks about Orion storage",
        read(db, bob, "Orion Postgres pgvector", [("team", team)], mode="hybrid"),
    )
    show_retrieve(
        "alice asks about review schedule",
        read(db, alice, "Thursday review", [("team", team)]),
    )

    section("ISOLATION — sales group cannot read platform team")
    show_retrieve(
        "cara (sales) queries team/platform",
        read(db, cara, "Orion Postgres", [("team", team)]),
    )
    deny(
        "cara write to team/platform",
        lambda: write(db, cara, "team", team, "noise", "chat"),
    )

    section("PROMOTE-FROM-PERSONAL pattern (optional handoff)")
    ensure_scope(db, alice, "personal", "alice")
    private = write(
        db,
        alice,
        "personal",
        "alice",
        "Draft note: consider HNSW cosine for Orion embeddings.",
        "scratch",
    )
    # After review, promote a copy into the team scope (source unchanged).
    promoted = db.promote(alice, private["id"], "team", team)
    maybe_drain(db)
    print("promoted", private["id"], "->", promoted["id"], "source=", promoted["source"])
    show_retrieve(
        "bob sees promoted embedding note",
        read(db, bob, "HNSW cosine embeddings", [("team", team)]),
    )

    if hasattr(db, "close"):
        db.close()
    print("\nDone: team assistant write/read sample.")


if __name__ == "__main__":
    main()
