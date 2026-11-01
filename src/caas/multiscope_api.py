"""Multi-scope API. Dev-only headers; production identity middleware required."""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .factory import open_memory
from .multiscope import Conflict, Denied, Principal

app = FastAPI(title="CaaS multi-scope", version="0.4")
memory = open_memory(os.getenv("CAAS_DATABASE_URL") or os.getenv("DATABASE_URL") or os.getenv("CAAS_SCOPED_DB", "scoped.db"))


class Scope(BaseModel):
    kind: str
    scope_id: str
    classification: str = "internal"


class Grant(BaseModel):
    kind: str
    scope_id: str
    subject: str
    permission: str


class Write(BaseModel):
    kind: str
    scope_id: str
    content: str
    source: str
    memory_type: str = "fact"
    classification: str = "internal"
    purpose: str = "assistant"


class Search(BaseModel):
    query: str
    scopes: list[tuple[str, str]]
    purpose: str = "assistant"
    limit: int = 20
    max_chars: int = 6000
    mode: str = Field(default="hybrid", pattern="^(hybrid|lexical|vector)$")


class Update(BaseModel):
    content: str = ""
    expected_version: int
    delete: bool = False


class Promote(BaseModel):
    target_kind: str
    target_id: str
    purpose: str = "assistant"


class Relate(BaseModel):
    src_label: str
    relation: str
    dst_label: str
    src_kind: str = "entity"
    dst_kind: str = "entity"
    memory_id: str | None = None


class Neighbors(BaseModel):
    label: str
    relation: str | None = None
    limit: int = 50


def principal(
    x_verified_tenant: str | None = Header(None),
    x_verified_subject: str | None = Header(None),
    x_verified_groups: str = Header(""),
):
    if os.getenv("CAAS_UNSAFE_DEV_HEADERS") != "1":
        raise HTTPException(503, "Verified identity middleware required")
    if not x_verified_tenant or not x_verified_subject:
        raise HTTPException(401, "Missing identity")
    return Principal(
        x_verified_tenant,
        x_verified_subject,
        frozenset(filter(None, x_verified_groups.split(","))),
    )


def run(fn):
    try:
        return fn()
    except Denied:
        raise HTTPException(403, "Forbidden")
    except KeyError:
        raise HTTPException(404, "Not found")
    except Conflict as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/healthz")
def health():
    backend = type(memory).__name__
    return {"status": "ok", "backend": backend}


@app.post("/v1/scopes")
def scope(req: Scope, p: Principal = Depends(principal)):
    return run(lambda: memory.create_scope(p, req.kind, req.scope_id, req.classification)) or {
        "ok": True
    }


@app.post("/v1/grants")
def grant(req: Grant, p: Principal = Depends(principal)):
    return run(
        lambda: memory.grant(p, req.kind, req.scope_id, req.subject, req.permission)
    ) or {"ok": True}


@app.delete("/v1/grants")
def revoke(req: Grant, p: Principal = Depends(principal)):
    return run(
        lambda: memory.revoke(p, req.kind, req.scope_id, req.subject, req.permission)
    ) or {"ok": True}


@app.post("/v1/memories")
def write(req: Write, p: Principal = Depends(principal)):
    return run(lambda: memory.write(p, **req.model_dump()))


@app.get("/v1/memories/{mid}")
def get(mid: str, p: Principal = Depends(principal)):
    return run(lambda: memory.get(p, mid))


@app.patch("/v1/memories/{mid}")
def update(mid: str, req: Update, p: Principal = Depends(principal)):
    return run(lambda: memory.revise(p, mid, **req.model_dump())) or {"deleted": True}


@app.post("/v1/memories/{mid}/promote")
def promote(mid: str, req: Promote, p: Principal = Depends(principal)):
    return run(lambda: memory.promote(p, mid, **req.model_dump()))


@app.post("/v1/context:retrieve")
def search(req: Search, p: Principal = Depends(principal)):
    kwargs = req.model_dump()
    # SQLite Memory has no mode kwarg
    if not hasattr(memory, "embedder"):
        kwargs.pop("mode", None)
    return run(lambda: memory.search(p, **kwargs))


@app.post("/v1/graph/relate")
def relate(req: Relate, p: Principal = Depends(principal)):
    if not hasattr(memory, "relate"):
        raise HTTPException(501, "Graph requires PostgreSQL backend")
    return run(lambda: memory.relate(p, **req.model_dump()))


@app.post("/v1/graph/neighbors")
def neighbors(req: Neighbors, p: Principal = Depends(principal)):
    if not hasattr(memory, "neighbors"):
        raise HTTPException(501, "Graph requires PostgreSQL backend")
    return run(lambda: memory.neighbors(p, req.label, relation=req.relation, limit=req.limit))


@app.post("/v1/admin/outbox:drain")
def drain(p: Principal = Depends(principal)):
    """Dev helper: process pending outbox projections synchronously."""
    if type(memory).__name__ != "PostgresMemory":
        raise HTTPException(501, "Outbox requires PostgreSQL backend")
    from .worker import process_batch

    return {"processed": process_batch(memory)}
