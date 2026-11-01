"""Shared helpers for assistant samples (in-process Memory / PostgresMemory)."""
from __future__ import annotations

import os
import uuid
from typing import Any

from caas.factory import open_memory
from caas.multiscope import Denied, Principal


def backend():
    """Open SQLite by default; Postgres when CAAS_DATABASE_URL is set."""
    url = os.getenv("CAAS_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if url.startswith("postgres"):
        return open_memory(url)
    # Unique on-disk SQLite so concurrent sample runs do not collide.
    path = os.getenv("CAAS_SCOPED_DB") or f"/tmp/caas-sample-{uuid.uuid4().hex}.db"
    return open_memory(path)


def principal(tenant: str, subject: str, *groups: str, clearance: str = "internal") -> Principal:
    return Principal(tenant, subject, frozenset(groups), clearance=clearance)


def ensure_scope(db, p: Principal, kind: str, scope_id: str, classification: str = "internal"):
    try:
        db.create_scope(p, kind, scope_id, classification)
    except Exception as exc:
        # UniqueViolation / IntegrityError on re-run
        name = type(exc).__name__
        if "Unique" in name or "Integrity" in name:
            if hasattr(db, "conn"):
                try:
                    db.conn.rollback()
                except Exception:
                    pass
            return
        raise


def write(db, p: Principal, kind: str, scope_id: str, content: str, source: str, **kw: Any):
    return db.write(p, kind, scope_id, content, source, **kw)


def read(db, p: Principal, query: str, scopes: list[tuple[str, str]], **kw: Any) -> dict:
    kwargs = dict(kw)
    if not hasattr(db, "embedder"):
        kwargs.pop("mode", None)
    return db.search(p, query, scopes, **kwargs)


def maybe_drain(db) -> int:
    if type(db).__name__ != "PostgresMemory":
        return 0
    from caas.worker import process_batch

    return process_batch(db)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def show_retrieve(label: str, result: dict) -> None:
    print(f"\n[{label}]")
    print("context:", result.get("context") or "(empty)")
    print("manifest:", result.get("manifest") or [])


def deny(label: str, fn) -> None:
    try:
        fn()
        print(f"[{label}] ERROR: expected denial")
    except Denied:
        print(f"[{label}] correctly denied")
