"""Multi-scope API. Dev-only headers; production identity middleware required."""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .factory import open_memory
from .multiscope import Conflict, Denied, Principal

app = FastAPI(title="CaaS multi-scope", version="0.5")
memory = open_memory(
    os.getenv("CAAS_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("CAAS_SCOPED_DB", "scoped.db")
)


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


class UpsertNode(BaseModel):
    label: str
    kind: str = "entity"
    attrs: dict = Field(default_factory=dict)
    memory_id: str | None = None


class Relate(BaseModel):
    src_label: str
    relation: str
    dst_label: str
    src_kind: str = "entity"
    dst_kind: str = "entity"
    attrs: dict = Field(default_factory=dict)
    memory_id: str | None = None
    replace: bool = True


class Unrelate(BaseModel):
    edge_id: str | None = None
    src_label: str | None = None
    relation: str | None = None
    dst_label: str | None = None
    src_kind: str = "entity"
    dst_kind: str = "entity"


class Neighbors(BaseModel):
    label: str
    relation: str | None = None
    direction: str = Field(default="both", pattern="^(out|in|both)$")
    kind: str = "entity"
    at: datetime | None = None
    limit: int = 50


class PathQuery(BaseModel):
    src_label: str
    dst_label: str
    max_hops: int = 3
    relation: str | None = None
    src_kind: str = "entity"
    dst_kind: str = "entity"
    at: datetime | None = None


class SubgraphQuery(BaseModel):
    label: str
    hops: int = 1
    kind: str = "entity"
    at: datetime | None = None
    limit: int = 100


class HistoryQuery(BaseModel):
    node_id: str | None = None
    edge_id: str | None = None
    label: str | None = None
    kind: str = "entity"


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


def require_graph():
    if not hasattr(memory, "relate"):
        raise HTTPException(501, "Graph requires PostgreSQL backend")


@app.get("/healthz")
def health():
    return {"status": "ok", "backend": type(memory).__name__, "version": "0.5"}


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
    payload = req.model_dump()
    payload["sid"] = payload.pop("scope_id")
    return run(lambda: memory.write(p, **payload))


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
    if not hasattr(memory, "embedder"):
        kwargs.pop("mode", None)
    return run(lambda: memory.search(p, **kwargs))


@app.post("/v1/graph/nodes")
def upsert_node(req: UpsertNode, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.upsert_node(p, **req.model_dump()))


@app.get("/v1/graph/nodes/{node_id}")
def get_node(
    node_id: str,
    at: datetime | None = Query(None),
    p: Principal = Depends(principal),
):
    require_graph()
    return run(lambda: memory.get_node(p, node_id=node_id, at=at))


@app.delete("/v1/graph/nodes/{node_id}")
def close_node(node_id: str, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.close_node(p, node_id))


@app.post("/v1/graph/relate")
def relate(req: Relate, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.relate(p, **req.model_dump()))


@app.post("/v1/graph/unrelate")
def unrelate(req: Unrelate, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.unrelate(p, **req.model_dump()))


@app.post("/v1/graph/neighbors")
def neighbors(req: Neighbors, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.neighbors(p, **req.model_dump()))


@app.post("/v1/graph/path")
def path(req: PathQuery, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.path(p, **req.model_dump()))


@app.post("/v1/graph/subgraph")
def subgraph(req: SubgraphQuery, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.subgraph(p, **req.model_dump()))


@app.post("/v1/graph/history")
def history(req: HistoryQuery, p: Principal = Depends(principal)):
    require_graph()
    return run(lambda: memory.history(p, **req.model_dump()))


@app.post("/v1/admin/outbox:drain")
def drain(p: Principal = Depends(principal)):
    if type(memory).__name__ != "PostgresMemory":
        raise HTTPException(501, "Outbox requires PostgreSQL backend")
    from .worker import process_batch

    return {"processed": process_batch(memory)}
