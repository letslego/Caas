# Enterprise Context-as-a-Service (CaaS)

Reference implementation of a governed enterprise context layer for agentic systems, with Google ADK-compatible session compaction.

## Architecture

Agent (Google ADK / other) → REST Context API → identity/policy → context compiler → scoped memory + federated retrieval (Glean, Databricks, Starburst) → provenance-bearing context manifest.

**Read path:** authenticate → authorize → retrieve from permitted sources → rank and budget → return citations and provenance.

**Write path:** validate scope → durable memory write → asynchronous projection/indexing (planned) → consolidation and retention.

ADK owns its session-event compaction; CaaS owns durable memory and enterprise context. Never compact authoritative source records. Summaries must retain decisions, identifiers, numbers, unresolved actions, provenance, and security scope. See docs/COMPACTION.md.

## Local development

```bash
pip install -e '.[dev]'
pytest -q
uvicorn caas.api:app --reload
```

Local SQLite is a development-only backing store. Enterprise connectors and authentication require real deployments and configuration. Do not expose this example API publicly.

## Status

Reference foundation, **not production ready**. Production work includes enterprise SSO/OIDC, authorization propagation, PostgreSQL, outbox workers, vector/graph projections, real source connectors, audit trails, and integration/evaluation tests.

## Repository

GitHub: https://github.com/letslego/Caas

## Multi-scope assistants (v0.3 reference)

The `caas.multiscope` module implements personal, team, project, organization, agent and task memory with tenant isolation, explicit read/write/admin grants, purpose and classification controls, versioned updates, tombstone deletion, controlled promotion, and provenance manifests. See [architecture](docs/MULTI_SCOPE.md) and [example](examples/multiscope_demo.py).

```bash
pip install -e '.[dev]'
pytest -q
python examples/multiscope_demo.py
# LOCAL DEVELOPMENT ONLY; never expose this header-authenticated demo publicly:
CAAS_UNSAFE_DEV_HEADERS=1 uvicorn caas.multiscope_api:app --host 127.0.0.1 --port 8080
```

The earlier `caas.api` remains a legacy single-purpose example. Use `caas.multiscope_api` for the new endpoints. Neither API is production hardened.

**Important:** This is an implemented reference foundation, not a complete enterprise deployment. Real OIDC authorization, PostgreSQL/RLS, durable workers, vector and temporal graph stores, enterprise connectors, and ADK integration verification remain outstanding. Never commit credentials or enterprise data to this public repository.
