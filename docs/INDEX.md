# CaaS documentation index

| Doc | Audience | Contents |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Everyone | Layers, read/write paths, trust boundaries |
| [API.md](API.md) | API consumers | Full REST reference (memory + graph) |
| [SDK.md](SDK.md) | App & agent authors | Python `CaasClient` + MCP server tools |
| [MULTI_SCOPE.md](MULTI_SCOPE.md) | Product / security | Six scopes, ACLs, lifecycle |
| [POSTGRES.md](POSTGRES.md) | Operators | Postgres, pgvector, RLS, outbox |
| [GRAPH.md](GRAPH.md) | Engineers | Temporal property graph model |
| [COMPACTION.md](COMPACTION.md) | ADK integrators | Session compaction vs durable memory |
| [../examples/README.md](../examples/README.md) | Developers | Personal / team / org assistant samples |

**Status:** reference foundation — not production ready. Dev header identity (`CAAS_UNSAFE_DEV_HEADERS=1`) is localhost-only.
