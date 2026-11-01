#!/usr/bin/env python3
"""Personal assistant: private read/write to a personal scope.

Only the owning subject can read or write. Personal scopes cannot be shared
via grants. Another user in the same tenant must see nothing.
"""
from __future__ import annotations

import sys
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
    alice = principal("acme", "alice")
    bob = principal("acme", "bob")

    section("Setup personal scope")
    ensure_scope(db, alice, "personal", "alice")
    print("scope: personal/alice owned by alice")

    section("WRITE — remember preferences and open work")
    pref = write(
        db,
        alice,
        "personal",
        "alice",
        "Alice prefers concise bullet summaries under 8 lines.",
        "conversation",
        memory_type="preference",
    )
    task = write(
        db,
        alice,
        "personal",
        "alice",
        "Open action: draft Q3 OKR review for Orion by Friday; blocker is missing ARR numbers.",
        "task-notes",
        memory_type="action",
    )
    print("wrote", pref["id"], "and", task["id"])
    maybe_drain(db)

    section("READ — personal assistant retrieves private context")
    show_retrieve(
        "alice asks about summaries",
        read(db, alice, "concise summaries", [("personal", "alice")]),
    )
    show_retrieve(
        "alice asks about Orion OKRs",
        read(db, alice, "Orion OKR Friday", [("personal", "alice")]),
    )

    section("ISOLATION — bob cannot read alice personal memory")
    show_retrieve(
        "bob queries alice personal scope",
        read(db, bob, "Orion OKR", [("personal", "alice")]),
    )
    deny(
        "bob write into alice personal",
        lambda: write(db, bob, "personal", "alice", "sneaky", "hack"),
    )
    deny(
        "alice cannot open personal scope as bob",
        lambda: ensure_scope(db, alice, "personal", "bob"),
    )

    section("REVISE — update preference with optimistic versioning")
    updated = db.revise(
        alice,
        pref["id"],
        "Alice prefers concise bullet summaries under 5 lines, with decisions first.",
        pref["version"],
    )
    print("revised to version", updated["version"])
    show_retrieve(
        "alice after revise",
        read(db, alice, "summaries decisions", [("personal", "alice")]),
    )

    if hasattr(db, "close"):
        db.close()
    print("\nDone: personal assistant write/read sample.")


if __name__ == "__main__":
    main()
