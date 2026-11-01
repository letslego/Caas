# Architecture

Enterprise Context-as-a-Service (CaaS) is a governed context layer for agentic systems. Google ADK owns short-lived session compaction and persona UX; CaaS owns durable scoped memory, hot working memory, profile/episodic/knowledge planes, retrieval, temporal graph, and operational controls.

NFRs (latency classes, durability, isolation, security): [NFR.md](NFR.md).

## Layered model

```
┌──────────────────────────────────────────────────────────────────────┐
│ Agents / assistants (personal · team · org) · ADK · MCP clients      │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ REST · SDK · MCP
┌─────────────────────────────▼────────────────────────────────────────┐
│ L1 Integration & identity                                            │
│ Verified principal (OIDC/mTLS planned; dev headers local-only)       │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│ L2 Policy & operational control                                      │
│ Grants · clearance×classification · purpose · caps · kill switch     │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│ L3 Context compiler — assemble()                                     │
│ Budgeted pack: working → profile → durable scopes → episodes →       │
│ knowledge → (optional) graph neighbors · timings_ms · manifest       │
└───┬──────────┬──────────┬──────────┬──────────┬──────────┬───────────┘
    │          │          │          │          │          │
 Working   Profile   Durable    Episodic  Knowledge  Graph/Vectors
 (hot)     (warm)    scoped     events    documents  (pgvector+TPG)
    │          │          │          │          │          │
    ▼          └──────────┴──────────┴──────────┴──────────┘
 Redis*                                                    │
 (opt.)                                         Postgres SoR (+ SQLite tests)
                                                outbox workers
```

\*Redis is optional. The reference ships an in-process CAS+TTL working store that implements the same interface.

## Memory planes

| Plane | Holds | NFR class | Mutability |
|---|---|---|---|
| **Working** | Recent session turns / tool results | Hot, ephemeral | CAS append; TTL; max turns |
| **Profile** | Typed per-user facts (`verbosity`, …) | Warm | Upsert / forget; revision bump |
| **Durable scoped** | personal/team/project/org/agent/task memories | Durable | Versioned write/revise/promote |
| **Episodic** | Timestamped events (decisions, tickets) | Warm/durable | Append + list by time |
| **Knowledge** | Ingested documents / chunks | Durable + ANN | Ingest; hybrid search |
| **Graph** | Temporal entities/relations | Durable eventual | Valid-time versions |
| **Operational** | Audit, step/spend caps, kill switch | Control plane | Append audit; set caps; fail-closed |

Multi-scope ACL (grants, no inheritance) continues to govern **durable scoped** reads/writes. Profile is private to `subject`. Working is keyed by `(tenant, subject, session)`. Knowledge/episodes are tenant-scoped with optional `user_id` restriction.

## Control flows

### assemble (read path for agents)

1. Resolve principal; check kill switch (reads may still be allowed; writes blocked).  
2. Load working turns for session (hot).  
3. Load profile facts (warm).  
4. Retrieve durable memories for requested scopes (authorize each).  
5. List recent episodes for subject/tenant.  
6. Search knowledge if `query` present.  
7. Pack sections under `max_chars` with priority order above.  
8. Return `{prompt, sections, manifest, timings_ms}`.

### write paths

| Intent | API | Notes |
|---|---|---|
| Session turn | `working.append` | Hot only |
| Preference/fact | `profile.set` | Subject-owned |
| Durable memory | existing `/v1/memories` | Outbox → vectors/graph |
| Episode | `episodes.record` | Durable event |
| Document | `knowledge.ingest` | Chunk + embed job |
| Cap / kill | `ops.*` | Admin/host only |

## Trust boundaries

- Tenant is a hard wall.  
- Never trust tenant/subject from model-controlled tool arguments without host binding.  
- Classification: `public < internal < confidential < restricted`.  
- Dev headers are not a production control plane.  
- Compaction rules: [COMPACTION.md](COMPACTION.md).

## Relationship to Memlayer

CaaS absorbs Memlayer’s **planes** (working, profile, knowledge, episodic, operational) and **assemble** semantics under CaaS **governance** (scopes, grants, clearance, Postgres/pgvector, temporal graph, MCP). Chatbot persona/reflection UX remains in the ADK host (see Memlayer Atlas); CaaS stays the durable/enterprise context substrate.

## Status

Reference foundation. Production still needs real OIDC, forced RLS app roles, Redis HA, learned rerankers, federated connectors, and adversarial tests.
