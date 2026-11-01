# PostgreSQL + pgvector backend

The multi-scope service selects backends via URL:

| URL / env | Backend |
|---|---|
| unset / file path / `:memory:` via `CAAS_SCOPED_DB` | SQLite (`caas.multiscope.Memory`) — unit tests & tiny demos |
| `postgresql://…` via `CAAS_DATABASE_URL` or `DATABASE_URL` | Postgres + pgvector (`caas.pgmemory.PostgresMemory`) |

## What ships in this reference

1. **Durable scoped memory** — same ACL / versioning / promotion semantics as SQLite.
2. **Tenant RLS** — policies filter on `current_setting('caas.tenant')`. Application sessions call `set_config` per transaction. Use a non-owner app role (or `FORCE ROW LEVEL SECURITY`) in real deployments; table owners bypass RLS by default in Postgres.
3. **Durable outbox** — every write/revise/delete enqueues `memory.upserted` / `memory.deleted`.
4. **pgvector projection** — worker embeds content into `memory_embeddings` (`vector(384)`, HNSW, cosine).
5. **Temporal graph** — `graph_nodes` / `graph_edges` with `valid_from` / `valid_to`. Worker projects co-mentions and `derived_from` on promotion; API exposes explicit `relate` / `neighbors`.
6. **Hybrid retrieve** — lexical + vector ranking (`mode=hybrid|lexical|vector`).

## Local setup

```bash
# docker compose (recommended)
docker compose up -d postgres
export CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas

pip install -e '.[dev,postgres]'
python -c 'from caas.postgres import migrate; migrate()'
# drain projections in-process for demos:
CAAS_UNSAFE_DEV_HEADERS=1 uvicorn caas.multiscope_api:app --host 127.0.0.1 --port 8080
# or run the worker:
caas-worker --once
```

Default embedder is deterministic feature hashing (`HashingEmbedder`). Swap via injecting `Embedder` into `PostgresMemory` for production models.

## Graph: do we need one?

Yes, but **not a separate graph database** for this reference. Enterprise context needs typed relationships over time (promotion lineage, entity co-mention, explicit agent assertions). Storing a **temporal property graph in Postgres** keeps tenant RLS, backups, and transactions unified with memory and vectors. Reach for Neo4j/Neptune only when path queries or graph algorithms outgrow SQL.

## Still out of scope

OIDC/mTLS identity, delegated source credentials, real Glean/Databricks/Starburst connectors, consent/erasure workflows, and adversarial security test suites remain separate work.
