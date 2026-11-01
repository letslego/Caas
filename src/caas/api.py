"""Legacy single-purpose Context API. Prefer `caas.multiscope_api`."""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .core import ContextService, Principal
from .persistence import SQLiteStore

app = FastAPI(title="CaaS legacy", version="0.2")
service = ContextService(SQLiteStore(os.getenv("CAAS_DB", "caas.db")))


class Retrieve(BaseModel):
    query: str
    max_chars: int = 4000


def _principal(
    x_verified_tenant: str | None = Header(None),
    x_verified_subject: str | None = Header(None),
    x_verified_groups: str = Header(""),
) -> Principal:
    if os.getenv("CAAS_UNSAFE_DEV_HEADERS") != "1":
        raise HTTPException(503, "Verified identity middleware required")
    if not x_verified_tenant or not x_verified_subject:
        raise HTTPException(401, "Missing identity")
    return Principal(
        x_verified_tenant,
        x_verified_subject,
        frozenset(filter(None, x_verified_groups.split(","))),
    )


@app.get("/healthz")
def health():
    return {"status": "ok", "backend": "legacy-sqlite"}


@app.post("/v1/context")
def retrieve(req: Retrieve, p: Principal = Depends(_principal)):
    try:
        return service.retrieve(p, req.query, req.max_chars)
    except PermissionError:
        raise HTTPException(403, "Forbidden")
