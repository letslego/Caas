# CaaS multi-scope memory architecture

Six independently governed scopes: personal, team, project, organization, agent, task.

## Identity and access
The identity provider supplies tenant, subject, groups, clearance and permitted purposes. Scope owner controls grants. Other users require explicit user or group grants; personal scopes cannot be shared. Tenant isolation and classification checks are mandatory. No automatic inheritance from organization to project, team or personal scope.

## Memory lifecycle
Create a scope, grant authorized readers/writers, write provenance-bearing memories, retrieve scoped context and manifest, revise with optimistic version checks, tombstone deleted records, and promote by explicitly copying to a destination where the actor has write rights. Promotion does not mutate the source.

## ADK compaction
Google ADK remains the session event compactor. CaaS retains durable scoped memory and context assembly. Do not compact task execution ledgers or source-of-truth enterprise documents. Keep decisions, identifiers, numbers, pending actions, uncertainty and provenance when summarizing.

## Local demo
Install with `pip install -e '.[dev]'`, run `uvicorn caas.multiscope_api:app --reload`. API intentionally rejects header identity by default. For **local-only** experimentation set `CAAS_UNSAFE_DEV_HEADERS=1` and supply X-Verified-Tenant / X-Verified-Subject headers. Never enable this in an externally accessible deployment.

## Not production ready
Replace SQLite with PostgreSQL and tenant RLS; integrate verified OIDC/mTLS and delegated source credentials; add source-level ACL enforcement, durable outbox/indexing, vector and temporal graph retrieval, real Glean/Databricks/Starburst connectors, audit retention, consent, erasure, and adversarial security tests.
