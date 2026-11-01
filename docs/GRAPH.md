# Temporal property graph

CaaS stores a **valid-time property graph in PostgreSQL** beside durable memories and pgvector projections. No separate graph database is required for the reference.

## Model

| Concept | Storage |
|---|---|
| Node identity | `graph_node_ids(id, tenant)` |
| Node versions | `graph_nodes(tenant, id, version, label, kind, attrs, valid_from, valid_to, …)` |
| Edge versions | `graph_edges(tenant, id, version, src, dst, relation, attrs, valid_from, valid_to, …)` |

`valid_to IS NULL` means **current**. Attribute updates close the current row (`valid_to = now`) and insert `version+1`. Deletes/unrelates only set `valid_to` (tombstone); history is retained.

## APIs

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/graph/nodes` | Upsert node (versioned attrs) |
| GET | `/v1/graph/nodes/{id}` | Read node as-of `?at=` |
| DELETE | `/v1/graph/nodes/{id}` | Close node + incident edges |
| POST | `/v1/graph/relate` | Assert edge (optional replace) |
| POST | `/v1/graph/unrelate` | Close edge |
| POST | `/v1/graph/neighbors` | Incident edges (`out`/`in`/`both`) |
| POST | `/v1/graph/path` | Bounded directed BFS |
| POST | `/v1/graph/subgraph` | N-hop neighborhood |
| POST | `/v1/graph/history` | All versions of a node/edge |

Worker projections also emit `co_mentions` and promotion `derived_from` edges via the durable outbox.

## SDK

```python
from caas import CaasClient

with CaasClient("http://127.0.0.1:8080", tenant="acme", subject="alice", groups=["platform"]) as c:
    c.relate("Orion", "depends_on", "Apollo", attrs={"priority": "P1"})
    print(c.path("Orion", "Apollo"))
    print(c.history(label="Orion"))
```

## MCP server

```bash
pip install -e '.[mcp,postgres]'
CAAS_BASE_URL=http://127.0.0.1:8080 \
CAAS_TENANT=acme CAAS_SUBJECT=alice CAAS_GROUPS=platform \
caas-mcp
```

Tools include `caas_graph_relate`, `caas_graph_neighbors`, `caas_graph_path`, `caas_graph_subgraph`, `caas_graph_history`, plus memory/retrieve helpers.

## When to leave Postgres

Stay on SQL until path queries, graph algorithms, or multi-hop fan-out outgrow recursive CTEs / BFS. Then project edges into Neo4j/Neptune while keeping Postgres as the system of record for tenant RLS and audit.
