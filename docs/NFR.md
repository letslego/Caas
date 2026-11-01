# Non-functional requirements (reference targets)

Industry-shaped NFRs for an enterprise context / memory service. **Targets are design goals for the reference**, not a hosted SLA. Measure with `pytest` latency smoke and future benches before claiming compliance.

## Quality attributes

| Attribute | Target (reference) | Mechanism in CaaS |
|---|---|---|
| **Availability** | Durable API designed for multi-instance stateless frontends | Postgres as shared SoR; working memory optionally Redis-backed |
| **Durability** | RPO ≈ 0 for committed durable writes | Postgres sync commit; outbox before ack returns |
| **Consistency** | Durable: read-your-writes within a tenant session; Working: CAS / last-writer with TTL | DB transactions; working compare-and-set revision |
| **Isolation** | Tenant hard wall; scope ACL; classification floor | SQL tenant predicates + RLS hooks; grants; clearance |
| **Latency (local warm)** | Working p99 ≤ 5 ms; profile p99 ≤ 5 ms; assemble p99 ≤ 50 ms; durable hybrid retrieve p99 ≤ 150 ms | In-process working store; budgeted assemble; pgvector HNSW |
| **Throughput** | Horizontal scale of API workers; durable limited by Postgres | Stateless API; connection pooling (psycopg) |
| **Security** | Least privilege; no body-trusted tenant; audited mutations | Principal from verified middleware; audit log; kill switch |
| **Privacy** | Retention classes; erasure of personal scope on request (API hook) | Tombstones + profile forget; org retention policies as memories |
| **Observability** | Structured audit; assemble section timings | `audit` table; assemble `timings_ms` in response |
| **Capacity** | Char/token budgets; step/spend caps per tenant/user/session | `assemble` budgets; operational caps |
| **Recoverability** | Durable recoverable from Postgres backups; working ephemeral | Document RPO/RTO with ops runbooks (deployment-specific) |

## Latency classes

| Class | Examples | Store |
|---|---|---|
| **Hot** | Working turns, kill-switch check | Process memory or Redis |
| **Warm** | Profile facts, recent episodes | Postgres/SQLite primary key reads |
| **Cold / ANN** | Hybrid durable + knowledge search | pgvector + lexical |

## Consistency matrix

| Plane | Write ack | Read visibility | Loss on crash |
|---|---|---|---|
| Working | After CAS in hot store | Immediate for that key | Yes (unless Redis AOF/replica configured) |
| Profile / Episodes / Knowledge meta | After SQL commit | After commit | No |
| Durable scoped memory | After SQL + outbox insert | After commit; vectors after worker | No for rows; vectors eventually consistent |
| Graph / embeddings | After worker | Eventually | Rebuildable from outbox/source |

## Security NFRs

1. Tenant id never accepted from model tool args or unverified JSON alone.  
2. Dev headers require explicit `CAAS_UNSAFE_DEV_HEADERS=1` and must not be enabled on public networks.  
3. Every durable mutation appends audit.  
4. Kill switch fails closed for writes when engaged.  
5. Caps enforce step/spend budgets before write side-effects.

## Mapping from Memlayer gaps

| Memlayer capability | NFR driver | CaaS plane |
|---|---|---|
| Redis working memory | Latency / session continuity | **Working** |
| Profile facts + revision cache | Latency / personalization | **Profile** |
| Episodes | Durable event recall | **Episodic** |
| Knowledge HNSW+BM25 | Retrieval quality | **Knowledge** (+ existing durable/pgvector) |
| assembleContext | Latency + capacity | **Context compiler** |
| Caps / kill switch / audit | Security / capacity | **Operational** |
| ADK Atlas persona | Agent UX | Integration (adapter; persona stays in ADK host) |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the layer diagram and control flows.
