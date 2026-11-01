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
