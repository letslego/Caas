"""MCP server exposing CaaS memory + temporal graph tools to agents.

Run (stdio):
  CAAS_BASE_URL=http://127.0.0.1:8080 \\
  CAAS_TENANT=acme CAAS_SUBJECT=alice CAAS_GROUPS=platform \\
  CAAS_UNSAFE_DEV_HEADERS=1 \\
  caas-mcp

The MCP process talks to a running CaaS API via the Python SDK. Prefer a
network-local API with verified identity middleware in production.
"""
from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .sdk import CaasClient, CaasError

mcp = FastMCP(
    "caas",
    instructions=(
        "Enterprise Context-as-a-Service: multi-scope durable memory, hybrid "
        "retrieve, and a temporal property graph. Use graph tools for typed "
        "relationships (depends_on, derived_from, ownership). Always pass "
        "explicit scopes for retrieve."
    ),
)


def _client() -> CaasClient:
    base = os.getenv("CAAS_BASE_URL", "http://127.0.0.1:8080")
    tenant = os.getenv("CAAS_TENANT")
    subject = os.getenv("CAAS_SUBJECT")
    if not tenant or not subject:
        raise RuntimeError("Set CAAS_TENANT and CAAS_SUBJECT for the MCP server")
    groups = [g for g in os.getenv("CAAS_GROUPS", "").split(",") if g]
    token = os.getenv("CAAS_TOKEN")
    return CaasClient(base, tenant=tenant, subject=subject, groups=groups, token=token)


def _ok(data: Any) -> str:
    return json.dumps(data, default=str)


def _err(exc: Exception) -> str:
    if isinstance(exc, CaasError):
        return json.dumps({"error": True, "status": exc.status, "detail": exc.detail})
    return json.dumps({"error": True, "detail": str(exc)})


@mcp.tool()
def caas_health() -> str:
    """Check CaaS API health and backend type."""
    try:
        with _client() as c:
            return _ok(c.health())
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_create_scope(kind: str, scope_id: str, classification: str = "internal") -> str:
    """Create a governed memory scope (personal/team/project/organization/agent/task)."""
    try:
        with _client() as c:
            return _ok(c.create_scope(kind, scope_id, classification))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_grant(kind: str, scope_id: str, subject: str, permission: str) -> str:
    """Grant read/write/admin on a non-personal scope to user:… or group:…."""
    try:
        with _client() as c:
            return _ok(c.grant(kind, scope_id, subject, permission))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_write_memory(
    kind: str,
    scope_id: str,
    content: str,
    source: str,
    memory_type: str = "fact",
    classification: str = "internal",
    purpose: str = "assistant",
) -> str:
    """Write a provenance-bearing memory into a scope."""
    try:
        with _client() as c:
            return _ok(
                c.write_memory(
                    kind,
                    scope_id,
                    content,
                    source,
                    memory_type=memory_type,
                    classification=classification,
                    purpose=purpose,
                )
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_retrieve_context(
    query: str,
    scopes_json: str,
    purpose: str = "assistant",
    limit: int = 20,
    max_chars: int = 6000,
    mode: str = "hybrid",
) -> str:
    """Retrieve scoped context. scopes_json is [[kind, scope_id], ...]. mode=hybrid|lexical|vector."""
    try:
        scopes = [tuple(s) for s in json.loads(scopes_json)]
        with _client() as c:
            return _ok(
                c.retrieve(
                    query,
                    scopes,
                    purpose=purpose,
                    limit=limit,
                    max_chars=max_chars,
                    mode=mode,
                )
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_promote_memory(
    memory_id: str, target_kind: str, target_id: str, purpose: str = "assistant"
) -> str:
    """Copy a memory into another scope where the actor has write rights."""
    try:
        with _client() as c:
            return _ok(c.promote_memory(memory_id, target_kind, target_id, purpose))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_upsert_node(
    label: str,
    kind: str = "entity",
    attrs_json: str = "{}",
    memory_id: str | None = None,
) -> str:
    """Upsert a temporal graph node (valid-time versioned attrs)."""
    try:
        with _client() as c:
            return _ok(
                c.upsert_node(label, kind, attrs=json.loads(attrs_json), memory_id=memory_id)
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_relate(
    src_label: str,
    relation: str,
    dst_label: str,
    src_kind: str = "entity",
    dst_kind: str = "entity",
    attrs_json: str = "{}",
    memory_id: str | None = None,
    replace: bool = True,
) -> str:
    """Assert a typed edge between nodes (closes prior same src/relation/dst when replace=true)."""
    try:
        with _client() as c:
            return _ok(
                c.relate(
                    src_label,
                    relation,
                    dst_label,
                    src_kind=src_kind,
                    dst_kind=dst_kind,
                    attrs=json.loads(attrs_json),
                    memory_id=memory_id,
                    replace=replace,
                )
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_unrelate(
    edge_id: str | None = None,
    src_label: str | None = None,
    relation: str | None = None,
    dst_label: str | None = None,
) -> str:
    """Close (tombstone) an edge by id or by src/relation/dst labels."""
    try:
        with _client() as c:
            return _ok(
                c.unrelate(
                    edge_id=edge_id,
                    src_label=src_label,
                    relation=relation,
                    dst_label=dst_label,
                )
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_neighbors(
    label: str,
    relation: str | None = None,
    direction: str = "both",
    kind: str = "entity",
    limit: int = 50,
) -> str:
    """List incident edges for a node as-of now. direction=out|in|both."""
    try:
        with _client() as c:
            return _ok(
                c.neighbors(
                    label,
                    relation=relation,
                    direction=direction,
                    kind=kind,
                    limit=limit,
                )
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_path(
    src_label: str,
    dst_label: str,
    max_hops: int = 3,
    relation: str | None = None,
) -> str:
    """Bounded directed path search over the temporal graph (as-of now)."""
    try:
        with _client() as c:
            return _ok(
                c.path(src_label, dst_label, max_hops=max_hops, relation=relation)
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_subgraph(label: str, hops: int = 1, kind: str = "entity") -> str:
    """Expand a neighborhood subgraph around a node."""
    try:
        with _client() as c:
            return _ok(c.subgraph(label, hops=hops, kind=kind))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_graph_history(
    label: str | None = None,
    node_id: str | None = None,
    edge_id: str | None = None,
    kind: str = "entity",
) -> str:
    """Return valid-time versions of a node or edge."""
    try:
        with _client() as c:
            return _ok(
                c.history(label=label, node_id=node_id, edge_id=edge_id, kind=kind)
            )
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_drain_outbox() -> str:
    """Process pending outbox projections (embeddings + graph) synchronously (dev helper)."""
    try:
        with _client() as c:
            return _ok(c.drain_outbox())
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_append_turn(session_id: str, role: str, content: str) -> str:
    """Append a hot working-memory turn for the session."""
    try:
        with _client() as c:
            return _ok(c.append_turn(session_id, role, content))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_set_profile_fact(key: str, value: str) -> str:
    """Set a typed profile fact for the bound subject."""
    try:
        with _client() as c:
            return _ok(c.set_profile_fact(key, value))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_record_episode(kind: str, title: str, detail: str = "") -> str:
    """Record an episodic event for the subject."""
    try:
        with _client() as c:
            return _ok(c.record_episode(kind, title, detail))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_ingest_document(title: str, content: str, source: str) -> str:
    """Ingest a knowledge document (chunked)."""
    try:
        with _client() as c:
            return _ok(c.ingest_document(title, content, source))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_assemble_context(
    session_id: str,
    query: str,
    scopes_json: str,
    max_chars: int = 8000,
) -> str:
    """Budgeted multi-plane context pack (working+profile+durable+episodes+knowledge)."""
    try:
        scopes = [tuple(s) for s in json.loads(scopes_json)]
        with _client() as c:
            return _ok(c.assemble(session_id, query, scopes, max_chars=max_chars))
    except Exception as e:
        return _err(e)


@mcp.tool()
def caas_set_kill_switch(engaged: bool, reason: str = "") -> str:
    """Engage or clear the tenant kill switch (host/admin)."""
    try:
        with _client() as c:
            return _ok(c.set_kill_switch(engaged, reason))
    except Exception as e:
        return _err(e)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
