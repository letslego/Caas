# Python SDK and MCP server

## Install

```bash
pip install -e '.[dev]'              # SDK (httpx) included
pip install -e '.[postgres,mcp]'     # DB + MCP server extras
```

## `CaasClient` (SDK)

```python
from caas import CaasClient

with CaasClient(
    "http://127.0.0.1:8080",
    tenant="acme",
    subject="alice",
    groups=["platform"],
    # token="…",  # optional Bearer for future OIDC gateways
) as c:
    c.create_scope("personal", "alice")
    m = c.write_memory("personal", "alice", "Prefers short reviews", "chat")
    ctx = c.retrieve("reviews", [("personal", "alice")], mode="hybrid")
    print(ctx["context"], ctx["manifest"])
```

### Construction

| Arg | Description |
|---|---|
| `base_url` | API origin |
| `tenant` / `subject` / `groups` | Sent as `X-Verified-*` (dev) |
| `token` | Optional `Authorization: Bearer` |
| `client` | Inject `httpx.Client` (tests) |

Raises `caas.CaasError` with `.status` and `.detail` on HTTP ≥ 400.

### Memory methods

| Method | API |
|---|---|
| `create_scope` | `POST /v1/scopes` |
| `grant` / `revoke` | `POST` / `DELETE /v1/grants` |
| `write_memory` | `POST /v1/memories` |
| `get_memory` | `GET /v1/memories/{id}` |
| `revise_memory` | `PATCH /v1/memories/{id}` |
| `promote_memory` | `POST /v1/memories/{id}/promote` |
| `retrieve` | `POST /v1/context:retrieve` |
| `drain_outbox` | `POST /v1/admin/outbox:drain` |
| `health` | `GET /healthz` |

### Graph methods

| Method | API |
|---|---|
| `upsert_node` / `get_node` / `close_node` | `/v1/graph/nodes` |
| `relate` / `unrelate` | `/v1/graph/relate` · `/unrelate` |
| `neighbors` / `path` / `subgraph` / `history` | matching `/v1/graph/*` |

See also [GRAPH.md](GRAPH.md) and [API.md](API.md).

### In-process alternative

For scripts/tests without HTTP:

```python
from caas import open_memory, Principal
db = open_memory()  # or postgresql://…
p = Principal("acme", "alice")
db.create_scope(p, "personal", "alice")
```

---

## MCP server (`caas-mcp`)

Exposes CaaS as Model Context Protocol tools over **stdio**. The server is an HTTP client to a running API.

```bash
CAAS_UNSAFE_DEV_HEADERS=1 caas-api --host 127.0.0.1 --port 8080 &

CAAS_BASE_URL=http://127.0.0.1:8080 \
CAAS_TENANT=acme \
CAAS_SUBJECT=alice \
CAAS_GROUPS=platform \
caas-mcp
```

### Environment

| Var | Required | Purpose |
|---|---|---|
| `CAAS_BASE_URL` | no (default `http://127.0.0.1:8080`) | API base |
| `CAAS_TENANT` | yes | Tenant |
| `CAAS_SUBJECT` | yes | Subject |
| `CAAS_GROUPS` | no | Comma-separated groups |
| `CAAS_TOKEN` | no | Bearer token |

### Tools

| Tool | Role |
|---|---|
| `caas_health` | Backend health |
| `caas_create_scope` | Create scope |
| `caas_grant` | Grant ACL |
| `caas_write_memory` | Write memory |
| `caas_retrieve_context` | Scoped retrieve (`scopes_json`) |
| `caas_promote_memory` | Promote copy |
| `caas_graph_upsert_node` | Upsert node |
| `caas_graph_relate` | Assert edge |
| `caas_graph_unrelate` | Close edge |
| `caas_graph_neighbors` | Incident edges |
| `caas_graph_path` | Bounded path |
| `caas_graph_subgraph` | Neighborhood |
| `caas_graph_history` | Version history |
| `caas_drain_outbox` | Sync projections |

All tools return JSON strings (`error: true` payload on failure).

### Cursor / MCP client snippet

```json
{
  "mcpServers": {
    "caas": {
      "command": "caas-mcp",
      "env": {
        "CAAS_BASE_URL": "http://127.0.0.1:8080",
        "CAAS_TENANT": "acme",
        "CAAS_SUBJECT": "alice",
        "CAAS_GROUPS": "platform"
      }
    }
  }
}
```

---

## Assistant patterns (SDK)

**Personal** — only `("personal", subject)` in retrieve scopes; never grant personal.  
**Team** — create team scope, `grant(group:…, read)`, write decisions, retrieve with `mode=hybrid`.  
**Organization** — higher classification; require clearance; combine org+team scopes in one retrieve when authorized.

Runnable samples: [examples/README.md](../examples/README.md).
