"""Temporal property graph operations (valid-time versioning in Postgres)."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from .multiscope import Principal
from .postgres import tenant_session

Direction = Literal["out", "in", "both"]
ENTITY_RE = re.compile(r"\b([A-Z][a-zA-Z0-9_-]{1,63})\b")


def utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: _iso(v) for k, v in dict(row).items()}


def node_id_for(tenant: str, kind: str, label: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant}:{kind}:{label.casefold()}").hex


class TemporalGraphMixin:
    """Mixin expecting `self.conn` and `self.log(cur, principal, action, resource)`."""

    def upsert_node(
        self,
        p: Principal,
        label: str,
        kind: str = "entity",
        attrs: dict[str, Any] | None = None,
        memory_id: str | None = None,
        *,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        label = label.strip()
        if not label:
            raise ValueError("label required")
        now = at or utc()
        nid = node_id_for(p.tenant, kind, label)
        attrs = attrs or {}
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                "INSERT INTO graph_node_ids (id, tenant) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (nid, p.tenant),
            )
            cur.execute(
                """SELECT version, attrs, label, kind FROM graph_nodes
                   WHERE tenant=%s AND id=%s AND valid_to IS NULL""",
                (p.tenant, nid),
            )
            current = cur.fetchone()
            if current is None:
                cur.execute(
                    """INSERT INTO graph_nodes
                       (tenant, id, version, label, kind, attrs, valid_from, memory_id, created_by)
                       VALUES (%s,%s,1,%s,%s,%s::jsonb,%s,%s,%s)
                       RETURNING *""",
                    (p.tenant, nid, label, kind, json.dumps(attrs), now, memory_id, p.subject),
                )
                row = cur.fetchone()
                self.log(cur, p, "graph.node.create", nid)
                return _serialize(row)  # type: ignore[return-value]

            if (
                current["label"] == label
                and current["kind"] == kind
                and dict(current["attrs"] or {}) == attrs
            ):
                cur.execute(
                    """SELECT * FROM graph_nodes
                       WHERE tenant=%s AND id=%s AND valid_to IS NULL""",
                    (p.tenant, nid),
                )
                return _serialize(cur.fetchone())  # type: ignore[return-value]

            new_version = int(current["version"]) + 1
            cur.execute(
                """UPDATE graph_nodes SET valid_to=%s
                   WHERE tenant=%s AND id=%s AND valid_to IS NULL""",
                (now, p.tenant, nid),
            )
            cur.execute(
                """INSERT INTO graph_nodes
                   (tenant, id, version, label, kind, attrs, valid_from, memory_id, created_by)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                   RETURNING *""",
                (
                    p.tenant,
                    nid,
                    new_version,
                    label,
                    kind,
                    json.dumps(attrs),
                    now,
                    memory_id,
                    p.subject,
                ),
            )
            row = cur.fetchone()
            self.log(cur, p, "graph.node.revise", nid)
            return _serialize(row)  # type: ignore[return-value]

    def get_node(
        self,
        p: Principal,
        *,
        node_id: str | None = None,
        label: str | None = None,
        kind: str = "entity",
        at: datetime | None = None,
    ) -> dict[str, Any]:
        at = at or utc()
        with tenant_session(self.conn, p.tenant) as cur:
            if node_id:
                cur.execute(
                    """SELECT * FROM graph_nodes
                       WHERE tenant=%s AND id=%s
                         AND valid_from <= %s
                         AND (valid_to IS NULL OR valid_to > %s)
                       ORDER BY version DESC LIMIT 1""",
                    (p.tenant, node_id, at, at),
                )
            elif label:
                cur.execute(
                    """SELECT * FROM graph_nodes
                       WHERE tenant=%s AND lower(label)=lower(%s) AND kind=%s
                         AND valid_from <= %s
                         AND (valid_to IS NULL OR valid_to > %s)
                       ORDER BY version DESC LIMIT 1""",
                    (p.tenant, label, kind, at, at),
                )
            else:
                raise ValueError("node_id or label required")
            row = cur.fetchone()
        if row is None:
            raise KeyError(node_id or label)
        return _serialize(row)  # type: ignore[return-value]

    def close_node(
        self, p: Principal, node_id: str, *, at: datetime | None = None
    ) -> dict[str, Any]:
        now = at or utc()
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """UPDATE graph_nodes SET valid_to=%s
                   WHERE tenant=%s AND id=%s AND valid_to IS NULL
                   RETURNING *""",
                (now, p.tenant, node_id),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(node_id)
            cur.execute(
                """UPDATE graph_edges SET valid_to=%s
                   WHERE tenant=%s AND valid_to IS NULL
                     AND (src=%s OR dst=%s)""",
                (now, p.tenant, node_id, node_id),
            )
            self.log(cur, p, "graph.node.close", node_id)
        return _serialize(row)  # type: ignore[return-value]

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
        replace: bool = True,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        relation = relation.strip()
        if not relation:
            raise ValueError("relation required")
        now = at or utc()
        src = self.upsert_node(p, src_label, src_kind, memory_id=memory_id, at=now)
        dst = self.upsert_node(p, dst_label, dst_kind, memory_id=memory_id, at=now)
        edge_id = uuid.uuid4().hex
        with tenant_session(self.conn, p.tenant) as cur:
            if replace:
                cur.execute(
                    """UPDATE graph_edges SET valid_to=%s
                       WHERE tenant=%s AND src=%s AND dst=%s AND relation=%s
                         AND valid_to IS NULL""",
                    (now, p.tenant, src["id"], dst["id"], relation),
                )
            cur.execute(
                """INSERT INTO graph_edges
                   (tenant, id, version, src, dst, relation, attrs, valid_from,
                    memory_id, created_by)
                   VALUES (%s,%s,1,%s,%s,%s,%s::jsonb,%s,%s,%s)
                   RETURNING *""",
                (
                    p.tenant,
                    edge_id,
                    src["id"],
                    dst["id"],
                    relation,
                    json.dumps(attrs or {}),
                    now,
                    memory_id,
                    p.subject,
                ),
            )
            edge = cur.fetchone()
            self.log(cur, p, "graph.edge.create", edge_id)
        return {
            "edge": _serialize(edge),
            "src": src,
            "relation": relation,
            "dst": dst,
            "id": edge_id,
        }

    def unrelate(
        self,
        p: Principal,
        *,
        edge_id: str | None = None,
        src_label: str | None = None,
        relation: str | None = None,
        dst_label: str | None = None,
        src_kind: str = "entity",
        dst_kind: str = "entity",
        at: datetime | None = None,
    ) -> dict[str, Any]:
        now = at or utc()
        with tenant_session(self.conn, p.tenant) as cur:
            if edge_id:
                cur.execute(
                    """UPDATE graph_edges SET valid_to=%s
                       WHERE tenant=%s AND id=%s AND valid_to IS NULL
                       RETURNING *""",
                    (now, p.tenant, edge_id),
                )
                rows = cur.fetchall()
            else:
                if not (src_label and relation and dst_label):
                    raise ValueError("edge_id or src/relation/dst required")
                src = node_id_for(p.tenant, src_kind, src_label)
                dst = node_id_for(p.tenant, dst_kind, dst_label)
                cur.execute(
                    """UPDATE graph_edges SET valid_to=%s
                       WHERE tenant=%s AND src=%s AND dst=%s AND relation=%s
                         AND valid_to IS NULL
                       RETURNING *""",
                    (now, p.tenant, src, dst, relation),
                )
                rows = cur.fetchall()
            if not rows:
                raise KeyError(edge_id or f"{src_label}-{relation}->{dst_label}")
            self.log(cur, p, "graph.edge.close", rows[0]["id"])
        return {"closed": [_serialize(r) for r in rows]}

    def neighbors(
        self,
        p: Principal,
        label: str,
        *,
        relation: str | None = None,
        direction: Direction = "both",
        kind: str = "entity",
        at: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        at = at or utc()
        if not 1 <= limit <= 500:
            raise ValueError("limit out of range")
        with tenant_session(self.conn, p.tenant) as cur:
            cur.execute(
                """SELECT id FROM graph_nodes
                   WHERE tenant=%s AND lower(label)=lower(%s) AND kind=%s
                     AND valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)
                   ORDER BY version DESC LIMIT 1""",
                (p.tenant, label, kind, at, at),
            )
            node = cur.fetchone()
            if not node:
                return []

            if direction == "out":
                dir_sql, dir_params = "e.src=%s", [node["id"]]
            elif direction == "in":
                dir_sql, dir_params = "e.dst=%s", [node["id"]]
            else:
                dir_sql, dir_params = "(e.src=%s OR e.dst=%s)", [node["id"], node["id"]]

            rel_sql = "AND e.relation=%s" if relation else ""
            params: list[Any] = [at, at, at, at, p.tenant, at, at, *dir_params]
            if relation:
                params.append(relation)
            params.append(limit)
            cur.execute(
                f"""SELECT e.id, e.version, e.relation, e.attrs, e.memory_id,
                           e.valid_from, e.valid_to, e.src, e.dst,
                           sn.label AS src_label, sn.kind AS src_kind,
                           dn.label AS dst_label, dn.kind AS dst_kind
                    FROM graph_edges e
                    JOIN graph_nodes sn ON sn.tenant=e.tenant AND sn.id=e.src
                      AND sn.valid_from <= %s AND (sn.valid_to IS NULL OR sn.valid_to > %s)
                    JOIN graph_nodes dn ON dn.tenant=e.tenant AND dn.id=e.dst
                      AND dn.valid_from <= %s AND (dn.valid_to IS NULL OR dn.valid_to > %s)
                    WHERE e.tenant=%s
                      AND e.valid_from <= %s AND (e.valid_to IS NULL OR e.valid_to > %s)
                      AND {dir_sql}
                      {rel_sql}
                    LIMIT %s""",
                params,
            )
            return [_serialize(r) for r in cur.fetchall()]  # type: ignore[misc]

    def path(
        self,
        p: Principal,
        src_label: str,
        dst_label: str,
        *,
        max_hops: int = 3,
        relation: str | None = None,
        src_kind: str = "entity",
        dst_kind: str = "entity",
        at: datetime | None = None,
    ) -> dict[str, Any]:
        if not 1 <= max_hops <= 6:
            raise ValueError("max_hops out of range")
        at = at or utc()
        start = self.get_node(p, label=src_label, kind=src_kind, at=at)
        goal = self.get_node(p, label=dst_label, kind=dst_kind, at=at)
        frontier: list[tuple[str, list[str], list[dict[str, Any]]]] = [
            (start["id"], [start["id"]], [])
        ]
        seen = {start["id"]}
        with tenant_session(self.conn, p.tenant) as cur:
            while frontier:
                node, path_ids, path_edges = frontier.pop(0)
                if len(path_ids) - 1 >= max_hops:
                    continue
                if relation:
                    cur.execute(
                        """SELECT e.id, e.src, e.dst, e.relation, e.attrs
                           FROM graph_edges e
                           WHERE e.tenant=%s AND e.src=%s AND e.relation=%s
                             AND e.valid_from <= %s
                             AND (e.valid_to IS NULL OR e.valid_to > %s)""",
                        (p.tenant, node, relation, at, at),
                    )
                else:
                    cur.execute(
                        """SELECT e.id, e.src, e.dst, e.relation, e.attrs
                           FROM graph_edges e
                           WHERE e.tenant=%s AND e.src=%s
                             AND e.valid_from <= %s
                             AND (e.valid_to IS NULL OR e.valid_to > %s)""",
                        (p.tenant, node, at, at),
                    )
                for edge in cur.fetchall():
                    nxt = edge["dst"]
                    if nxt in seen:
                        continue
                    new_path = path_ids + [nxt]
                    new_edges = path_edges + [_serialize(edge)]  # type: ignore[list-item]
                    if nxt == goal["id"]:
                        labels = []
                        for nid in new_path:
                            cur.execute(
                                """SELECT id, label, kind FROM graph_nodes
                                   WHERE tenant=%s AND id=%s
                                     AND valid_from <= %s
                                     AND (valid_to IS NULL OR valid_to > %s)
                                   ORDER BY version DESC LIMIT 1""",
                                (p.tenant, nid, at, at),
                            )
                            labels.append(_serialize(cur.fetchone()))
                        return {
                            "found": True,
                            "nodes": labels,
                            "edges": new_edges,
                            "hops": len(new_edges),
                        }
                    seen.add(nxt)
                    frontier.append((nxt, new_path, new_edges))
        return {"found": False, "nodes": [], "edges": [], "hops": 0}

    def history(
        self,
        p: Principal,
        *,
        node_id: str | None = None,
        edge_id: str | None = None,
        label: str | None = None,
        kind: str = "entity",
    ) -> list[dict[str, Any]]:
        with tenant_session(self.conn, p.tenant) as cur:
            if edge_id:
                cur.execute(
                    """SELECT * FROM graph_edges
                       WHERE tenant=%s AND id=%s ORDER BY version""",
                    (p.tenant, edge_id),
                )
            else:
                if not node_id and label:
                    node_id = node_id_for(p.tenant, kind, label)
                if not node_id:
                    raise ValueError("node_id, label, or edge_id required")
                cur.execute(
                    """SELECT * FROM graph_nodes
                       WHERE tenant=%s AND id=%s ORDER BY version""",
                    (p.tenant, node_id),
                )
            return [_serialize(r) for r in cur.fetchall()]  # type: ignore[misc]

    def subgraph(
        self,
        p: Principal,
        label: str,
        *,
        hops: int = 1,
        kind: str = "entity",
        at: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if not 1 <= hops <= 3:
            raise ValueError("hops out of range")
        at = at or utc()
        root = self.get_node(p, label=label, kind=kind, at=at)
        nodes: dict[str, dict[str, Any]] = {root["id"]: root}
        edges: dict[str, dict[str, Any]] = {}
        frontier = {root["id"]}
        for _ in range(hops):
            nxt: set[str] = set()
            for nid in list(frontier):
                with tenant_session(self.conn, p.tenant) as cur:
                    cur.execute(
                        """SELECT e.*, sn.label AS src_label, dn.label AS dst_label
                           FROM graph_edges e
                           JOIN graph_nodes sn ON sn.tenant=e.tenant AND sn.id=e.src
                             AND sn.valid_from <= %s AND (sn.valid_to IS NULL OR sn.valid_to > %s)
                           JOIN graph_nodes dn ON dn.tenant=e.tenant AND dn.id=e.dst
                             AND dn.valid_from <= %s AND (dn.valid_to IS NULL OR dn.valid_to > %s)
                           WHERE e.tenant=%s AND (e.src=%s OR e.dst=%s)
                             AND e.valid_from <= %s AND (e.valid_to IS NULL OR e.valid_to > %s)
                           LIMIT %s""",
                        (at, at, at, at, p.tenant, nid, nid, at, at, limit),
                    )
                    for e in cur.fetchall():
                        edges[e["id"]] = _serialize(e)  # type: ignore[assignment]
                        for other in (e["src"], e["dst"]):
                            if other in nodes:
                                continue
                            cur.execute(
                                """SELECT * FROM graph_nodes
                                   WHERE tenant=%s AND id=%s
                                     AND valid_from <= %s
                                     AND (valid_to IS NULL OR valid_to > %s)
                                   ORDER BY version DESC LIMIT 1""",
                                (p.tenant, other, at, at),
                            )
                            n = cur.fetchone()
                            if n:
                                nodes[other] = _serialize(n)  # type: ignore[assignment]
                                nxt.add(other)
            frontier = nxt
        return {"root": root, "nodes": list(nodes.values()), "edges": list(edges.values())}

    def extract_entities(self, content: str) -> list[str]:
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
