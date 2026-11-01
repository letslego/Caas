"""PostgreSQL multi-scope memory with pgvector recall, outbox, and temporal graph."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg

from .embeddings import Embedder, default_embedder, vector_literal
from .multiscope import SCOPES, LEVELS, Principal, Denied, Conflict
from .postgres import connect, migrate, tenant_session

ENTITY_RE = re.compile(r"\b([A-Z][a-zA-Z0-9_-]{1,63})\b")


def utc() -> datetime:
    return datetime.now(timezone.utc)


class PostgresMemory:
    """Same behavioral surface as `caas.multiscope.Memory`, backed by Postgres."""

    def __init__(
        self,
        url: str | None = None,
        *,
        embedder: Embedder | None = None,
        auto_migrate: bool = True,
    ):
        if auto_migrate:
            migrate(url)
        self.url = url
        self.embedder = embedder or default_embedder()
        self.conn = connect(url)

    def close(self) -> None:
        self.conn.close()

    def _row(self, r: dict[str, Any] | None) -> dict[str, Any] | None:
        if r is None:
            return None
        out = dict(r)
        for key in ("created_at",):
            if isinstance(out.get(key), datetime):
                out[key] = out[key].astimezone(timezone.utc).isoformat()
        return out

    def log(self, cur: psycopg.Cursor, p: Principal, action: str, resource: str) -> None:
        cur.execute(
            "INSERT INTO audit (at, tenant, actor, action, resource) VALUES (%s,%s,%s,%s,%s)",
            (utc(), p.tenant, p.subject, action, resource),
        )

    def enqueue(
        self,
        cur: psycopg.Cursor,
        p: Principal,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        cur.execute(
            """INSERT INTO outbox (tenant, aggregate_type, aggregate_id, event_type, payload)
               VALUES (%s,%s,%s,%s,%s::jsonb)""",
            (p.tenant, aggregate_type, aggregate_id, event_type, json.dumps(payload)),
        )

    def scope(self, p: Principal, kind: str, sid: str) -> dict[str, Any] | None:
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                "SELECT * FROM scopes WHERE tenant=%s AND kind=%s AND id=%s",
                (p.tenant, kind, sid),
            )
            return cur.fetchone()

    def allowed(self, p: Principal, kind: str, sid: str, permission: str) -> bool:
        s = self.scope(p, kind, sid)
        if not s or LEVELS.get(p.clearance, -1) < LEVELS[s["classification"]]:
            return False
        if kind == "personal":
            return sid == p.subject
        if s["owner"] == p.subject:
            return True
        subjects = ["user:" + p.subject] + ["group:" + g for g in p.groups]
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """SELECT 1 FROM grants
                   WHERE tenant=%s AND kind=%s AND scope_id=%s
                     AND permission = ANY(%s)
                     AND subject = ANY(%s)
                   LIMIT 1""",
                (p.tenant, kind, sid, [permission, "admin"], subjects),
            )
            return cur.fetchone() is not None

    def create_scope(
        self, p: Principal, kind: str, sid: str, classification: str = "internal"
    ) -> None:
        if kind not in SCOPES or classification not in LEVELS or not sid:
            raise ValueError("Invalid scope")
        if kind == "personal" and sid != p.subject:
            raise Denied("Personal scope owner mismatch")
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                "INSERT INTO scopes VALUES (%s,%s,%s,%s,%s)",
                (p.tenant, kind, sid, p.subject, classification),
            )
            self.log(cur, p, "scope.create", kind + "/" + sid)

    def grant(
        self, p: Principal, kind: str, sid: str, subject: str, permission: str
    ) -> None:
        if (
            kind == "personal"
            or permission not in {"read", "write", "admin"}
            or not subject.startswith(("user:", "group:"))
        ):
            raise ValueError("Invalid grant")
        if not self.allowed(p, kind, sid, "admin"):
            raise Denied("Grant denied")
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """INSERT INTO grants VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (p.tenant, kind, sid, subject, permission),
            )
            self.log(cur, p, "grant", kind + "/" + sid + "/" + subject)

    def revoke(
        self, p: Principal, kind: str, sid: str, subject: str, permission: str
    ) -> None:
        if not self.allowed(p, kind, sid, "admin"):
            raise Denied("Revoke denied")
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """DELETE FROM grants WHERE tenant=%s AND kind=%s AND scope_id=%s
                   AND subject=%s AND permission=%s""",
                (p.tenant, kind, sid, subject, permission),
            )
            self.log(cur, p, "revoke", kind + "/" + sid + "/" + subject)

    def write(
        self,
        p: Principal,
        kind: str,
        sid: str,
        content: str,
        source: str,
        memory_type: str = "fact",
        classification: str = "internal",
        purpose: str = "assistant",
        origin_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.allowed(p, kind, sid, "write"):
            raise Denied("Write denied")
        if purpose not in p.purposes or classification not in LEVELS:
            raise Denied("Purpose/classification denied")
        scope = self.scope(p, kind, sid)
        if (
            LEVELS[classification] > LEVELS.get(p.clearance, -1)
            or LEVELS[classification] < LEVELS[scope["classification"]]
        ):
            raise Denied("Classification denied")
        if not content.strip() or not source.strip():
            raise ValueError("Content/source required")
        mid = uuid.uuid4().hex
        now = utc()
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """INSERT INTO memories VALUES
                   (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    mid,
                    p.tenant,
                    kind,
                    sid,
                    content,
                    source,
                    memory_type,
                    classification,
                    purpose,
                    1,
                    "active",
                    p.subject,
                    now,
                    origin_id,
                ),
            )
            cur.execute(
                "INSERT INTO revisions VALUES (%s,%s,%s,%s,%s,%s)",
                (mid, 1, content, "active", p.subject, now),
            )
            self.enqueue(
                cur,
                p,
                "memory",
                mid,
                "memory.upserted",
                {
                    "id": mid,
                    "content": content,
                    "kind": kind,
                    "scope_id": sid,
                    "purpose": purpose,
                    "classification": classification,
                    "status": "active",
                    "origin_id": origin_id,
                },
            )
            self.log(cur, p, "write", mid)
        return self.get(p, mid, purpose)

    def get(
        self, p: Principal, mid: str, purpose: str = "assistant"
    ) -> dict[str, Any]:
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                "SELECT * FROM memories WHERE tenant=%s AND id=%s AND status='active'",
                (p.tenant, mid),
            )
            r = cur.fetchone()
        if r is None:
            raise KeyError(mid)
        if (
            purpose not in p.purposes
            or r["purpose"] != purpose
            or LEVELS.get(p.clearance, -1) < LEVELS[r["classification"]]
            or not self.allowed(p, r["kind"], r["scope_id"], "read")
        ):
            raise Denied("Read denied")
        return self._row(r)  # type: ignore[return-value]

    def search(
        self,
        p: Principal,
        query: str,
        scopes: list[tuple[str, str]],
        purpose: str = "assistant",
        limit: int = 20,
        max_chars: int = 6000,
        *,
        mode: str = "hybrid",
    ) -> dict[str, Any]:
        if purpose not in p.purposes or not 1 <= limit <= 100 or not 1 <= max_chars <= 100000:
            raise Denied("Invalid query")
        words = [w.casefold() for w in query.split() if w]
        if not words and mode != "vector":
            return {"context": "", "items": [], "manifest": []}

        permitted: list[tuple[str, str]] = []
        for kind, sid in {tuple(s) for s in scopes}:
            if self.allowed(p, kind, sid, "read"):
                permitted.append((kind, sid))
        if not permitted:
            return {"context": "", "items": [], "manifest": []}

        scored: dict[str, tuple[float, dict[str, Any]]] = {}

        # Lexical pass
        if mode in ("hybrid", "lexical") and words:
            with tenant_session(self.conn, p.tenant) as cur:
                for kind, sid in permitted:
                    cur.execute(
                        """SELECT * FROM memories
                           WHERE tenant=%s AND kind=%s AND scope_id=%s
                             AND purpose=%s AND status='active'""",
                        (p.tenant, kind, sid, purpose),
                    )
                    for r in cur.fetchall():
                        if LEVELS.get(p.clearance, -1) < LEVELS[r["classification"]]:
                            continue
                        content = r["content"].casefold()
                        if not any(w in content for w in words):
                            continue
                        score = float(sum(content.count(w) for w in words))
                        scored[r["id"]] = (score, self._row(r))  # type: ignore[arg-type]

        # Vector pass (requires projected embeddings)
        if mode in ("hybrid", "vector"):
            qvec = vector_literal(self.embedder.embed([query])[0])
            with tenant_session(self.conn, p.tenant) as cur:
                for kind, sid in permitted:
                    cur.execute(
                        """SELECT m.*, 1 - (e.embedding <=> %s::vector) AS score
                           FROM memory_embeddings e
                           JOIN memories m ON m.id = e.memory_id
                           WHERE e.tenant=%s AND e.kind=%s AND e.scope_id=%s
                             AND e.purpose=%s AND e.status='active'
                             AND m.status='active'
                           ORDER BY e.embedding <=> %s::vector
                           LIMIT %s""",
                        (qvec, p.tenant, kind, sid, purpose, qvec, limit),
                    )
                    for r in cur.fetchall():
                        if LEVELS.get(p.clearance, -1) < LEVELS[r["classification"]]:
                            continue
                        score = float(r.pop("score") or 0.0)
                        # Boost hybrid: add lexical + vector
                        prev = scored.get(r["id"])
                        combined = score + (prev[0] if prev else 0.0)
                        scored[r["id"]] = (combined, self._row(r))  # type: ignore[arg-type]

        ranked = sorted(scored.values(), key=lambda t: t[0], reverse=True)
        items: list[dict[str, Any]] = []
        budget = max_chars
        for _, r in ranked:
            if len(items) >= limit:
                break
            if len(r["content"]) <= budget:
                items.append(r)
                budget -= len(r["content"])
        return {
            "context": "\n\n".join(r["content"] for r in items),
            "items": items,
            "manifest": [
                {
                    "id": r["id"],
                    "source": r["source"],
                    "version": r["version"],
                    "scope": r["kind"] + "/" + r["scope_id"],
                }
                for r in items
            ],
        }

    def revise(
        self,
        p: Principal,
        mid: str,
        content: str,
        expected_version: int,
        delete: bool = False,
    ) -> dict[str, Any] | None:
        r = self.get(p, mid)
        if not self.allowed(p, r["kind"], r["scope_id"], "write"):
            raise Denied("Update denied")
        if not delete and not content.strip():
            raise ValueError("Empty content")
        new_content = "" if delete else content
        new_status = "deleted" if delete else "active"
        now = utc()
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """UPDATE memories SET content=%s, version=version+1, status=%s
                   WHERE id=%s AND version=%s AND status='active'
                   RETURNING id""",
                (new_content, new_status, mid, expected_version),
            )
            if cur.fetchone() is None:
                raise Conflict("Version conflict")
            cur.execute(
                "INSERT INTO revisions VALUES (%s,%s,%s,%s,%s,%s)",
                (mid, expected_version + 1, new_content, new_status, p.subject, now),
            )
            self.enqueue(
                cur,
                p,
                "memory",
                mid,
                "memory.deleted" if delete else "memory.upserted",
                {
                    "id": mid,
                    "content": new_content,
                    "kind": r["kind"],
                    "scope_id": r["scope_id"],
                    "purpose": r["purpose"],
                    "classification": r["classification"],
                    "status": new_status,
                },
            )
            self.log(cur, p, "delete" if delete else "revise", mid)
        return None if delete else self.get(p, mid)

    def promote(
        self,
        p: Principal,
        mid: str,
        target_kind: str,
        target_id: str,
        purpose: str = "assistant",
    ) -> dict[str, Any]:
        source = self.get(p, mid, purpose)
        if not self.allowed(p, target_kind, target_id, "write"):
            raise Denied("Promotion denied")
        return self.write(
            p,
            target_kind,
            target_id,
            source["content"],
            "promotion:" + mid,
            source["memory_type"],
            source["classification"],
            purpose,
            mid,
        )

    # --- Temporal graph API -------------------------------------------------

    def upsert_node(
        self,
        p: Principal,
        label: str,
        kind: str = "entity",
        attrs: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        label = label.strip()
        if not label:
            raise ValueError("label required")
        now = utc()
        node_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{p.tenant}:{kind}:{label.casefold()}").hex
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """SELECT id FROM graph_nodes
                   WHERE tenant=%s AND id=%s AND valid_to IS NULL""",
                (p.tenant, node_id),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """INSERT INTO graph_nodes
                       (id, tenant, label, kind, attrs, valid_from, memory_id)
                       VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (
                        node_id,
                        p.tenant,
                        label,
                        kind,
                        json.dumps(attrs or {}),
                        now,
                        memory_id,
                    ),
                )
                self.log(cur, p, "graph.node", node_id)
        return {"id": node_id, "label": label, "kind": kind}

    def relate(
        self,
        p: Principal,
        src_label: str,
        relation: str,
        dst_label: str,
        *,
        src_kind: str = "entity",
        dst_kind: str = "entity",
        attrs: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        src = self.upsert_node(p, src_label, src_kind, memory_id=memory_id)
        dst = self.upsert_node(p, dst_label, dst_kind, memory_id=memory_id)
        now = utc()
        edge_id = uuid.uuid4().hex
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """INSERT INTO graph_edges
                   (id, tenant, src, dst, relation, attrs, valid_from, memory_id)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (
                    edge_id,
                    p.tenant,
                    src["id"],
                    dst["id"],
                    relation,
                    json.dumps(attrs or {}),
                    now,
                    memory_id,
                ),
            )
            self.log(cur, p, "graph.edge", edge_id)
        return {
            "id": edge_id,
            "src": src,
            "relation": relation,
            "dst": dst,
        }

    def neighbors(
        self,
        p: Principal,
        label: str,
        *,
        relation: str | None = None,
        at: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        at = at or utc()
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """SELECT n.id FROM graph_nodes n
                   WHERE n.tenant=%s AND lower(n.label)=lower(%s)
                     AND n.valid_from <= %s
                     AND (n.valid_to IS NULL OR n.valid_to > %s)
                   LIMIT 1""",
                (p.tenant, label, at, at),
            )
            node = cur.fetchone()
            if not node:
                return []
            if relation:
                cur.execute(
                    """SELECT e.id, e.relation, e.attrs, e.memory_id,
                              sn.label AS src_label, dn.label AS dst_label
                       FROM graph_edges e
                       JOIN graph_nodes sn ON sn.id = e.src
                       JOIN graph_nodes dn ON dn.id = e.dst
                       WHERE e.tenant=%s AND (e.src=%s OR e.dst=%s)
                         AND e.relation=%s
                         AND e.valid_from <= %s
                         AND (e.valid_to IS NULL OR e.valid_to > %s)
                       LIMIT %s""",
                    (p.tenant, node["id"], node["id"], relation, at, at, limit),
                )
            else:
                cur.execute(
                    """SELECT e.id, e.relation, e.attrs, e.memory_id,
                              sn.label AS src_label, dn.label AS dst_label
                       FROM graph_edges e
                       JOIN graph_nodes sn ON sn.id = e.src
                       JOIN graph_nodes dn ON dn.id = e.dst
                       WHERE e.tenant=%s AND (e.src=%s OR e.dst=%s)
                         AND e.valid_from <= %s
                         AND (e.valid_to IS NULL OR e.valid_to > %s)
                       LIMIT %s""",
                    (p.tenant, node["id"], node["id"], at, at, limit),
                )
            return list(cur.fetchall())

    def extract_entities(self, content: str) -> list[str]:
        """Lightweight capitalized-token heuristic for demo projection."""
        stop = {"The", "A", "An", "And", "Or", "But", "If", "When", "This", "That"}
        seen: list[str] = []
        for m in ENTITY_RE.finditer(content):
            tok = m.group(1)
            if tok in stop or tok in seen:
                continue
            seen.append(tok)
            if len(seen) >= 8:
                break
        return seen
