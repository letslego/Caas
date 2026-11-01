#!/usr/bin/env python3
"""End-to-end assistant flow: personal → team → organization promotion.

Shows how an idea moves across governance boundaries without mutating sources.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    backend,
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
    alice = principal("acme", "alice", "platform", clearance="confidential")
    bob = principal("acme", "bob", "platform", clearance="confidential")
    sam = principal("acme", "sam", "security", "platform", clearance="confidential")
    team = "platform-" + uuid.uuid4().hex[:6]
    org = "acme-corp-" + uuid.uuid4().hex[:6]

    section("1) Personal assistant captures a draft")
    ensure_scope(db, alice, "personal", "alice")
    draft = write(
        db,
        alice,
        "personal",
        "alice",
        "Proposal: require purpose tags on every CaaS memory write; default purpose=assistant.",
        "scratchpad",
    )
    show_retrieve("alice personal", read(db, alice, "purpose tags", [("personal", "alice")]))

    section("2) Promote into team for review")
    ensure_scope(db, alice, "team", team)
    db.grant(alice, "team", team, "group:platform", "read")
    db.grant(alice, "team", team, "user:alice", "write")
    team_copy = db.promote(alice, draft["id"], "team", team)
    maybe_drain(db)
    show_retrieve("bob team", read(db, bob, "purpose tags", [("team", team)]))
    print("source still personal:", db.get(alice, draft["id"])["scope_id"])

    section("3) After approval, promote into organization policy scope")
    ensure_scope(db, sam, "organization", org, "confidential")
    db.grant(sam, "organization", org, "group:platform", "read")
    db.grant(sam, "organization", org, "group:security", "read")
    db.grant(sam, "organization", org, "user:sam", "write")
    # Team member cannot write org; security owner promotes/writes.
    org_mem = write(
        db,
        sam,
        "organization",
        org,
        "Policy adopted: every CaaS memory write requires a purpose tag; default purpose=assistant.",
        "promotion:" + team_copy["id"],
        memory_type="policy",
        classification="confidential",
        origin_id=team_copy["id"],
    )
    maybe_drain(db)
    show_retrieve(
        "alice org+team context",
        read(
            db,
            alice,
            "purpose tag policy",
            [("organization", org), ("team", team)],
        ),
    )

    if hasattr(db, "relate"):
        section("4) Graph lineage across layers")
        db.relate(sam, "PurposeTagPolicy", "adopted_from", "TeamProposal", memory_id=org_mem["id"])
        db.upsert_node(alice, "TeamProposal", attrs={"memory_id": team_copy["id"]})
        print(db.path(sam, "PurposeTagPolicy", "TeamProposal"))

    print("\nFlow complete: personal draft → team review → org policy.")
    if hasattr(db, "close"):
        db.close()


if __name__ == "__main__":
    main()
