# ADK session compaction vs CaaS durable memory

Google ADK owns **session-event compaction**. CaaS owns **durable scoped memory** and enterprise context assembly.

## Rules

- Never compact authoritative source records (tickets, docs, warehouse rows, ledgers).
- Do not collapse task execution ledgers into opaque summaries.
- When summarizing conversational context, retain:
  - decisions and their owners
  - identifiers (IDs, ticket keys, account numbers as permitted by classification)
  - numbers and constraints
  - unresolved actions and open questions
  - provenance (source system / URI / memory id)
  - security scope (tenant, classification, purpose)

## Boundary

| Concern | Owner |
|---|---|
| Short-lived chat event reduction | Google ADK |
| Multi-scope durable memory | CaaS |
| Vector / graph projections | CaaS outbox workers |
| Source-of-truth enterprise systems | Federated connectors (Glean, Databricks, Starburst) |

Compaction output may be *written into* CaaS as a memory with explicit provenance (`source=adk-compaction:…`), but CaaS must not treat that summary as a replacement for the underlying records.
