#!/usr/bin/env python3
"""Organization assistant: org-wide governed memory.

Organization scopes hold cross-team policies and decisions. Access is never
inherited automatically from org → team → personal; every reader/writer needs
an explicit grant (or ownership).
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
    # Org policy owner (security/platform lead)
    owner = principal("acme", "sam", "security", "platform", clearance="confidential")
    # Platform engineer with org read
    alice = principal("acme", "alice", "platform", clearance="internal")
    # Contractor with no org grant
    vendor = principal("acme", "vendor1", "vendors", clearance="internal")

    org = "acme-corp-" + uuid.uuid4().hex[:6]
    team = "platform-" + uuid.uuid4().hex[:6]

    section("Setup organization scope (confidential)")
    ensure_scope(db, owner, "organization", org, classification="confidential")
    # Owner can admin; grant org read to security + platform groups.
    db.grant(owner, "organization", org, "group:security", "read")
    db.grant(owner, "organization", org, "group:platform", "read")
    db.grant(owner, "organization", org, "user:sam", "write")
    print("org grants: security/platform=read, sam=write; classification=confidential")

    section("WRITE — organization policies and decisions")
    retention = write(
        db,
        owner,
        "organization",
        org,
        "Policy: CaaS audit logs retain 365 days; personal memory erasure requests must complete within 30 days.",
        "policy-catalog",
        memory_type="policy",
        classification="confidential",
    )
    sso = write(
        db,
        owner,
        "organization",
        org,
        "Decision: production CaaS identity must use OIDC; CAAS_UNSAFE_DEV_HEADERS is forbidden outside localhost demos.",
        "security-review",
        memory_type="decision",
        classification="confidential",
    )
    print("wrote", retention["id"], "and", sso["id"])
    maybe_drain(db)

    if hasattr(db, "relate"):
        section("GRAPH — org policy lineage")
        db.relate(
            owner,
            "CaaS",
            "governed_by",
            "OIDC",
            memory_id=sso["id"],
            attrs={"env": "production"},
        )
        print("path CaaS -> OIDC:", db.path(owner, "CaaS", "OIDC"))

    section("READ — authorized org assistants")
    # alice has platform group → read grant, clearance internal < confidential?
    # LEVELS: internal=1, confidential=2 — alice clearance internal cannot read confidential.
    show_retrieve(
        "alice (internal) queries confidential org (expect empty/denied via clearance)",
        read(db, alice, "OIDC audit retention", [("organization", org)]),
    )

    # Elevate alice clearance for the org assistant persona
    alice_conf = principal("acme", "alice", "platform", clearance="confidential")
    show_retrieve(
        "alice (confidential) org assistant retrieve",
        read(db, alice_conf, "OIDC audit retention", [("organization", org)]),
    )
    show_retrieve(
        "sam retrieves erasure SLA",
        read(db, owner, "erasure 30 days", [("organization", org)]),
    )

    section("ISOLATION — vendor and under-cleared subjects")
    show_retrieve(
        "vendor queries org",
        read(db, vendor, "OIDC", [("organization", org)]),
    )
    deny(
        "vendor write org policy",
        lambda: write(
            db,
            vendor,
            "organization",
            org,
            "bad",
            "chat",
            classification="confidential",
        ),
    )

    section("CROSS-SCOPE — org context + team context in one retrieve")
    ensure_scope(db, alice, "team", team)
    db.grant(alice, "team", team, "group:platform", "read")
    db.grant(alice, "team", team, "user:alice", "write")
    write(
        db,
        alice,
        "team",
        team,
        "Team note: local demos may set CAAS_UNSAFE_DEV_HEADERS=1 on 127.0.0.1 only.",
        "runbook",
    )
    maybe_drain(db)
    show_retrieve(
        "alice_conf reads org + team together",
        read(
            db,
            alice_conf,
            "CAAS_UNSAFE_DEV_HEADERS OIDC",
            [("organization", org), ("team", team)],
        ),
    )

    if hasattr(db, "close"):
        db.close()
    print("\nDone: organization assistant write/read sample.")


if __name__ == "__main__":
    main()
