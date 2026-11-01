"""Temporal property graph tests (Postgres required)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("psycopg")

DSN = os.getenv("CAAS_DATABASE_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN or not DSN.startswith("postgres"),
    reason="Set CAAS_DATABASE_URL",
)


@pytest.fixture()
def mem():
    from caas.embeddings import HashingEmbedder
    from caas.pgmemory import PostgresMemory

    m = PostgresMemory(DSN, embedder=HashingEmbedder(), auto_migrate=True)
    yield m
    m.close()


def P(tenant, subject="alice"):
    from caas.multiscope import Principal

    return Principal(tenant, subject)


def test_versioned_attrs_and_asof(mem):
    t = "g-" + uuid.uuid4().hex[:8]
    p = P(t)
    n1 = mem.upsert_node(p, "Apollo", attrs={"status": "planned"})
    assert n1["version"] == 1
    t1 = datetime.now(timezone.utc)
    n2 = mem.upsert_node(p, "Apollo", attrs={"status": "active"})
    assert n2["version"] == 2
    hist = mem.history(p, label="Apollo")
    assert len(hist) == 2
    assert hist[0]["valid_to"] is not None
    assert hist[0]["attrs"]["status"] == "planned"
    assert mem.get_node(p, label="Apollo")["attrs"]["status"] == "active"
    assert mem.get_node(p, label="Apollo", at=t1)["attrs"]["status"] in {"planned", "active"}


def test_relate_path_unrelate(mem):
    t = "g-" + uuid.uuid4().hex[:8]
    p = P(t)
    mem.relate(p, "Orion", "depends_on", "Apollo")
    mem.relate(p, "Apollo", "part_of", "Platform")
    path = mem.path(p, "Orion", "Platform", max_hops=3)
    assert path["found"] is True
    assert path["hops"] == 2
    nbrs = mem.neighbors(p, "Orion", direction="out", relation="depends_on")
    assert len(nbrs) == 1
    mem.unrelate(p, src_label="Orion", relation="depends_on", dst_label="Apollo")
    assert mem.neighbors(p, "Orion", relation="depends_on") == []
    assert mem.path(p, "Orion", "Platform", max_hops=3)["found"] is False


def test_subgraph_and_close(mem):
    t = "g-" + uuid.uuid4().hex[:8]
    p = P(t)
    edge = mem.relate(p, "Alpha", "links", "Beta")
    sub = mem.subgraph(p, "Alpha", hops=1)
    assert len(sub["nodes"]) >= 2
    assert any(e["id"] == edge["id"] for e in sub["edges"])
    mem.close_node(p, edge["src"]["id"])
    assert mem.neighbors(p, "Alpha") == []
