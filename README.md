# Enterprise Context-as-a-Service (CaaS)

Reference implementation of a governed enterprise context layer for agentic systems, with Google ADK-compatible session compaction.

## Architecture

Agent (Google ADK / other) → REST Context API → identity/policy → context compiler → scoped memory + federated retrieval (Glean, Databricks, Starburst) → provenance-bearing context manifest.

**Read path:** authenticate → authorize → retrieve from permitted sources → rank and budget → return citations and provenance.

**Write path:** validate scope → durable memory write → asynchronous outbox projection (pgvector + temporal graph) → consolidation and retention.

ADK owns its session-event compaction; CaaS owns durable memory and enterprise context. Never compact authoritative source records. Summaries must retain decisions, identifiers, numbers, unresolved actions, provenance, and security scope. See [docs/COMPACTION.md](docs/COMPACTION.md).

## Local development

### SQLite (unit tests / tiny demos)

```bash
pip install -e '.[dev]'
pytest -q
python examples/multiscope_demo.py
# LOCAL DEVELOPMENT ONLY; never expose this header-authenticated demo publicly:
CAAS_UNSAFE_DEV_HEADERS=1 uvicorn caas.multiscope_api:app --host 127.0.0.1 --port 8080
```

### PostgreSQL + pgvector (recommended reference path)

```bash
docker compose up -d postgres
export CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas
pip install -e '.[dev,postgres]'
pytest -q
python examples/postgres_demo.py
caas-worker --once
CAAS_UNSAFE_DEV_HEADERS=1 caas-api --host 127.0.0.1 --port 8080
```

See [docs/POSTGRES.md](docs/POSTGRES.md) for schema, RLS, outbox, hybrid retrieve, and graph guidance.

## Multi-scope assistants (v0.4)

The `caas.multiscope` / `caas.pgmemory` modules implement personal, team, project, organization, agent and task memory with tenant isolation, explicit read/write/admin grants, purpose and classification controls, versioned updates, tombstone deletion, controlled promotion, provenance manifests, durable outbox indexing, pgvector recall, and a temporal property graph. See [architecture](docs/MULTI_SCOPE.md) and [examples](examples/).

The earlier `caas.api` remains a legacy single-purpose example. Use `caas.multiscope_api` for the new endpoints. Neither API is production hardened.

## Status

Reference foundation, **not production ready**. Remaining production work includes enterprise SSO/OIDC, authorization propagation, non-owner DB roles with forced RLS, real embedding models, real source connectors, audit retention/consent/erasure, and integration/evaluation tests.

## Repository

GitHub: https://github.com/letslego/Caas

**Important:** Never commit credentials or enterprise data to this public repository.
