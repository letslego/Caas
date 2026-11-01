# Architecture layers

Enterprise Context-as-a-Service (CaaS) is a governed context layer for agentic systems. Google ADK (or another agent runtime) owns short-lived session compaction; CaaS owns durable scoped memory, retrieval, and provenance.

```
┌─────────────────────────────────────────────────────────────┐
│  Assistants / Agents (personal, team, org)                  │
│  ADK · custom agents · MCP clients                          │
└─────────────┬───────────────────────────────┬───────────────┘
              │ SDK / REST / MCP              │
┌─────────────▼───────────────────────────────▼───────────────┐
│  API layer — caas.multiscope_api                            │
│  Identity headers (dev) or future OIDC middleware           │
│  Request validation · error mapping (403/404/409/422)       │
└─────────────┬───────────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────────┐
│  Policy & scope layer — Principal, grants, classification   │
│  Tenant isolation · purpose checks · clearance levels       │
└─────────────┬───────────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────────┐
│  Context compiler / memory service                          │
│  Write · revise · promote · retrieve (budgeted + ranked)    │
│  Manifest with citations / versions / scopes                │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│ Durable      │  │ Vector       │  │ Temporal property    │
│ memory       │  │ projection   │  │ graph                │
│ (Postgres /  │  │ (pgvector)   │  │ (valid-time nodes/   │
│  SQLite)     │  │ via outbox   │  │  edges)              │
└──────────────┘  └──────────────┘  └──────────────────────┘
       │
       ▼  (planned)
┌──────────────────────────────────────┐
│ Federated sources: Glean / Databricks│
│ / Starburst — ACL-aware connectors   │
└──────────────────────────────────────┘
```

## Layers (detail)

### 1. Assistant / agent layer
Personal, team, and organization assistants call CaaS to **write** durable facts/decisions and **read** scoped context. They must never treat compacted chat as source-of-truth. Samples: `examples/personal_assistant.py`, `team_assistant.py`, `organization_assistant.py`.

### 2. Integration surface
| Surface | Module | Use when |
|---|---|---|
| REST | `caas.multiscope_api` | Any HTTP client |
| Python SDK | `caas.sdk.CaasClient` | Apps / services |
| MCP | `caas.mcp_server` (`caas-mcp`) | Tool-using agents |
| In-process | `caas.factory.open_memory` | Unit tests / local scripts |

### 3. Identity & policy
`Principal(tenant, subject, groups, clearance, purposes)` is resolved by middleware. Dev mode accepts `X-Verified-*` headers only when `CAAS_UNSAFE_DEV_HEADERS=1`. Authorization is **explicit grants** (no org→team→personal inheritance). Personal scopes are non-shareable.

### 4. Memory service
Creates scopes; writes versioned memories with provenance; revises with optimistic concurrency; tombstones deletes; promotes by **copy**; retrieves with lexical and/or vector ranking under a character budget; returns a **manifest**.

### 5. Storage & projections
- **System of record:** `memories` (+ `revisions`, `audit`)
- **Outbox:** durable events for async workers
- **pgvector:** `memory_embeddings` for semantic recall
- **Graph:** versioned nodes/edges with `valid_from` / `valid_to`

### 6. Federation (planned)
Glean / Databricks / Starburst connectors enforce source ACLs and attach provenance into the same manifest shape.

## Read path

1. Authenticate principal  
2. Authorize each requested `(kind, scope_id)` for `read`  
3. Filter by purpose + clearance ≥ classification  
4. Lexical and/or vector candidate generation  
5. Rank, apply `limit` / `max_chars` budget  
6. Return `{context, items, manifest}`

## Write path

1. Authenticate + authorize `write` on scope  
2. Validate purpose, classification vs clearance and scope floor  
3. Insert memory + revision + audit (+ outbox on Postgres)  
4. Worker projects embeddings and graph edges asynchronously  

## Trust boundaries

- Tenant is a hard wall (SQL filters + optional RLS).  
- Classification ladder: `public < internal < confidential < restricted`.  
- Dev header identity is **not** a production control plane.  
- Summaries must retain decisions, identifiers, numbers, open actions, provenance, and security scope ([COMPACTION.md](COMPACTION.md)).
