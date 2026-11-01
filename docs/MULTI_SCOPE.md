# CaaS multi-scope memory architecture

Six independently governed scopes: personal, team, project, organization, agent, task.

## Identity and access
The identity provider supplies tenant, subject, groups, clearance and permitted purposes. Scope owner controls grants. Other users require explicit user or group grants; personal scopes cannot be shared. Tenant isolation and classification checks are mandatory. No automatic inheritance from organization to project, team or personal scope.

## Memory lifecycle
Create a scope, grant authorized readers/writers, write provenance-bearing memories, retrieve scoped context and manifest, revise with optimistic version checks, tombstone deleted records, and promote by explicitly copying to a destination where the actor has write rights. Promotion does not mutate the source.

## Storage backends
- **SQLite** (`caas.multiscope.Memory`) for local unit tests.
- **PostgreSQL + pgvector** (`caas.pgmemory.PostgresMemory`) for the enterprise-shaped path: RLS tenant sessions, durable outbox, vector projections, and a temporal property graph. See [POSTGRES.md](POSTGRES.md).

## ADK compaction
Google ADK remains the session event compactor. CaaS retains durable scoped memory and context assembly. Do not compact task execution ledgers or source-of-truth enterprise documents. Keep decisions, identifiers, numbers, pending actions, uncertainty and provenance when summarizing. See [COMPACTION.md](COMPACTION.md).

## Local demo
Install with `pip install -e '.[dev]'`, run `uvicorn caas.multiscope_api:app --reload`. API intentionally rejects header identity by default. For **local-only** experimentation set `CAAS_UNSAFE_DEV_HEADERS=1` and supply X-Verified-Tenant / X-Verified-Subject headers. Never enable this in an externally accessible deployment.

```bash
export CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas
CAAS_UNSAFE_DEV_HEADERS=1 uvicorn caas.multiscope_api:app --host 127.0.0.1 --port 8080
caas-worker --once   # project embeddings + graph edges
CAAS_BASE_URL=http://127.0.0.1:8080 CAAS_TENANT=acme CAAS_SUBJECT=alice caas-mcp
```

Python SDK: `from caas import CaasClient`. Temporal graph details: [GRAPH.md](GRAPH.md).

## Not production ready
Replace demo header identity with verified OIDC/mTLS and delegated source credentials; add source-level ACL enforcement, real Glean/Databricks/Starburst connectors, audit retention, consent, erasure, and adversarial security tests. Run the app DB role as a non-owner (or FORCE RLS) so tenant policies cannot be bypassed.
