"""Outbox worker: project memory events into pgvector embeddings and temporal graph."""
from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .embeddings import vector_literal
from .pgmemory import PostgresMemory


def utc() -> datetime:
    return datetime.now(timezone.utc)


def process_batch(memory: PostgresMemory, batch_size: int = 50) -> int:
    """Claim and process pending outbox rows. Returns number processed."""
    processed = 0
    with memory.conn.transaction():
        with memory.conn.cursor() as cur:
            cur.execute(
                """SELECT id, tenant, aggregate_id, event_type, payload
                   FROM outbox
                   WHERE processed_at IS NULL
                   ORDER BY id
                   FOR UPDATE SKIP LOCKED
                   LIMIT %s""",
                (batch_size,),
            )
            rows = cur.fetchall()
            for row in rows:
                _handle(memory, cur, row)
                cur.execute(
                    "UPDATE outbox SET processed_at=%s WHERE id=%s",
                    (utc(), row["id"]),
                )
                processed += 1
    return processed


def _ensure_node(
    cur, tenant: str, node_id: str, label: str, kind: str, memory_id: str, now: datetime
) -> None:
    cur.execute(
        """SELECT id FROM graph_nodes
           WHERE tenant=%s AND id=%s AND valid_to IS NULL""",
        (tenant, node_id),
    )
    if cur.fetchone() is None:
        cur.execute(
            """INSERT INTO graph_nodes
               (id, tenant, label, kind, attrs, valid_from, memory_id)
               VALUES (%s,%s,%s,%s,'{}'::jsonb,%s,%s)""",
            (node_id, tenant, label, kind, now, memory_id),
        )


def _handle(memory: PostgresMemory, cur, row: dict[str, Any]) -> None:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    tenant = row["tenant"]
    mid = row["aggregate_id"]
    event = row["event_type"]
    now = utc()

    cur.execute("SELECT set_config('caas.tenant', %s, true)", (tenant,))

    if event == "memory.deleted" or payload.get("status") == "deleted":
        cur.execute("DELETE FROM memory_embeddings WHERE memory_id=%s", (mid,))
        cur.execute(
            """UPDATE graph_edges SET valid_to=%s
               WHERE tenant=%s AND memory_id=%s AND valid_to IS NULL""",
            (now, tenant, mid),
        )
        return

    if event != "memory.upserted":
        return

    content = payload.get("content") or ""
    lit = vector_literal(memory.embedder.embed([content])[0])
    cur.execute("DELETE FROM memory_embeddings WHERE memory_id=%s", (mid,))
    cur.execute(
        """INSERT INTO memory_embeddings
           (memory_id, tenant, kind, scope_id, purpose, classification, status,
            model, embedding, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)""",
        (
            mid,
            tenant,
            payload["kind"],
            payload["scope_id"],
            payload["purpose"],
            payload["classification"],
            payload.get("status", "active"),
            memory.embedder.model,
            lit,
            now,
        ),
    )

    entities = memory.extract_entities(content)
    node_ids: list[str] = []
    for label in entities:
        node_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"{tenant}:entity:{label.casefold()}"
        ).hex
        node_ids.append(node_id)
        _ensure_node(cur, tenant, node_id, label, "entity", mid, now)

    if payload.get("origin_id"):
        src = uuid.uuid5(
            uuid.NAMESPACE_URL, f"{tenant}:memory:{payload['origin_id']}"
        ).hex
        dst = uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant}:memory:{mid}").hex
        _ensure_node(cur, tenant, src, payload["origin_id"], "memory", mid, now)
        _ensure_node(cur, tenant, dst, mid, "memory", mid, now)
        cur.execute(
            """INSERT INTO graph_edges
               (id, tenant, src, dst, relation, attrs, valid_from, memory_id)
               VALUES (%s,%s,%s,%s,'derived_from','{}'::jsonb,%s,%s)""",
            (uuid.uuid4().hex, tenant, dst, src, now, mid),
        )

    for a, b in zip(node_ids, node_ids[1:]):
        cur.execute(
            """INSERT INTO graph_edges
               (id, tenant, src, dst, relation, attrs, valid_from, memory_id)
               VALUES (%s,%s,%s,%s,'co_mentions','{}'::jsonb,%s,%s)""",
            (uuid.uuid4().hex, tenant, a, b, now, mid),
        )


def run_forever(url: str | None = None, poll_seconds: float = 1.0) -> None:
    memory = PostgresMemory(url)
    try:
        while True:
            if process_batch(memory) == 0:
                time.sleep(poll_seconds)
    finally:
        memory.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CaaS outbox projection worker")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--url", default=None, help="PostgreSQL URL")
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args(argv)
    memory = PostgresMemory(args.url)
    try:
        if args.once:
            print(process_batch(memory))
        else:
            run_forever(args.url, args.poll)
    finally:
        memory.close()


if __name__ == "__main__":
    main()
