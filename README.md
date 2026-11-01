# Enterprise Context-as-a-Service (CaaS)

Reference implementation of a governed enterprise context layer for agentic systems, with Google ADK-compatible session compaction.

## Documentation

| Doc | Description |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | Documentation map |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, read/write paths, trust boundaries |
| [docs/API.md](docs/API.md) | Full REST API reference |
| [docs/SDK.md](docs/SDK.md) | Python SDK + MCP server |
| [docs/MULTI_SCOPE.md](docs/MULTI_SCOPE.md) | Scopes, ACLs, lifecycle |
| [docs/POSTGRES.md](docs/POSTGRES.md) | Postgres, pgvector, RLS, outbox |
| [docs/GRAPH.md](docs/GRAPH.md) | Temporal property graph |
| [docs/COMPACTION.md](docs/COMPACTION.md) | ADK compaction vs durable memory |
| [examples/README.md](examples/README.md) | Personal / team / org assistant samples |

## Architecture

Agent (Google ADK / other) → REST / SDK / MCP → identity/policy → context compiler → scoped memory + federated retrieval (Glean, Databricks, Starburst) → provenance-bearing context manifest.

**Read path:** authenticate → authorize → retrieve from permitted sources → rank and budget → return citations and provenance.

**Write path:** validate scope → durable memory write → asynchronous outbox projection (pgvector + temporal graph) → consolidation and retention.

ADK owns its session-event compaction; CaaS owns durable memory and enterprise context. Never compact authoritative source records. See [docs/COMPACTION.md](docs/COMPACTION.md).

## Assistant samples (read + write)

```bash
pip install -e '.[dev]'
python examples/personal_assistant.py      # private memory
python examples/team_assistant.py          # shared team + grants
python examples/organization_assistant.py  # org policy + clearance
python examples/assistants_promotion_flow.py
```

HTTP: start `CAAS_UNSAFE_DEV_HEADERS=1 caas-api --host 127.0.0.1 --port 8080`, then `bash examples/http/assistants_curl.sh`.

## Local development

### SQLite (unit tests / tiny demos)

```bash
pip install -e '.[dev]'
pytest -q
python examples/multiscope_demo.py
CAAS_UNSAFE_DEV_HEADERS=1 uvicorn caas.multiscope_api:app --host 127.0.0.1 --port 8080
```

### PostgreSQL + pgvector (recommended)

```bash
docker compose up -d postgres
export CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas
pip install -e '.[dev,postgres,mcp]'
pytest -q
python examples/postgres_demo.py
caas-worker --once
CAAS_UNSAFE_DEV_HEADERS=1 caas-api --host 127.0.0.1 --port 8080
CAAS_BASE_URL=http://127.0.0.1:8080 CAAS_TENANT=acme CAAS_SUBJECT=alice caas-mcp
```

## Multi-scope assistants (v0.5)

Personal, team, project, organization, agent, and task memory with tenant isolation, explicit grants, purpose/classification controls, versioning, promotion, provenance manifests, outbox → pgvector, and a temporal property graph. Use `caas.CaasClient` or `caas-mcp` from agents.

The earlier `caas.api` is legacy. Prefer `caas.multiscope_api`. Neither API is production hardened.

## Status

Reference foundation, **not production ready**. Remaining work: enterprise SSO/OIDC, forced RLS app roles, real embedding models, source connectors, consent/erasure, adversarial tests.

## Repository

GitHub: https://github.com/letslego/Caas

**Important:** Never commit credentials or enterprise data to this public repository. Never enable `CAAS_UNSAFE_DEV_HEADERS` on a public network.
