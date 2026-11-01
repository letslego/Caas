# REST API reference

Base app: `caas.multiscope_api:app` (v0.5).  
Legacy app: `caas.api:app` (single-purpose; prefer multi-scope).

## Auth (development only)

When `CAAS_UNSAFE_DEV_HEADERS=1`:

| Header | Required | Meaning |
|---|---|---|
| `X-Verified-Tenant` | yes | Tenant id |
| `X-Verified-Subject` | yes | User / agent subject |
| `X-Verified-Groups` | no | Comma-separated group names |

Without the env flag the API returns **503**. Production must replace this with verified OIDC/mTLS middleware.

## Common errors

| Status | Meaning |
|---|---|
| 401 | Missing identity headers |
| 403 | Denied by ACL / purpose / clearance |
| 404 | Memory or graph entity not found |
| 409 | Optimistic version conflict |
| 422 | Validation error |
| 501 | Feature needs PostgreSQL backend (graph/outbox) |
| 503 | Identity middleware not configured |

---

## Health

### `GET /healthz`
Returns `{status, backend, version}`. `backend` is `PostgresMemory` or `Memory`.

---

## Scopes & grants

### `POST /v1/scopes`
```json
{"kind":"team","scope_id":"platform","classification":"internal"}
```
`kind` ∈ `personal|team|project|organization|agent|task`.  
Personal: `scope_id` must equal the subject.

### `POST /v1/grants` / `DELETE /v1/grants`
```json
{"kind":"team","scope_id":"platform","subject":"group:platform","permission":"read"}
```
`permission` ∈ `read|write|admin`.  
`subject` must be `user:…` or `group:…`.  
Personal scopes cannot receive grants.

---

## Memories (write path)

### `POST /v1/memories`
```json
{
  "kind": "team",
  "scope_id": "platform",
  "content": "Orion uses Postgres + pgvector",
  "source": "design-review",
  "memory_type": "decision",
  "classification": "internal",
  "purpose": "assistant"
}
```
Returns the stored memory row (incl. `id`, `version`, `created_at`).

### `GET /v1/memories/{id}`
Fetch one active memory if the principal may read its scope.

### `PATCH /v1/memories/{id}`
```json
{"content":"updated text","expected_version":1,"delete":false}
```
Optimistic concurrency. `delete:true` tombstones the row.

### `POST /v1/memories/{id}/promote`
```json
{"target_kind":"team","target_id":"platform","purpose":"assistant"}
```
Copies into the target scope (`source=promotion:{id}`, `origin_id` set). Source unchanged.

---

## Context retrieve (read path)

### `POST /v1/context:retrieve`
```json
{
  "query": "Orion Postgres",
  "scopes": [["team","platform"],["personal","alice"]],
  "purpose": "assistant",
  "limit": 20,
  "max_chars": 6000,
  "mode": "hybrid"
}
```
`mode`: `hybrid` | `lexical` | `vector` (vector/hybrid need Postgres projections).

**Response**
```json
{
  "context": "…concatenated passages…",
  "items": [ {"id":"…","content":"…","source":"…", "…":"…"} ],
  "manifest": [ {"id":"…","source":"…","version":1,"scope":"team/platform"} ]
}
```

---

## Temporal graph (PostgreSQL)

### `POST /v1/graph/nodes`
Upsert versioned node: `{label, kind?, attrs?, memory_id?}`.

### `GET /v1/graph/nodes/{node_id}?at=<iso>`
Read node as-of timestamp (default now).

### `DELETE /v1/graph/nodes/{node_id}`
Close node and incident current edges (`valid_to=now`).

### `POST /v1/graph/relate`
```json
{
  "src_label":"Orion","relation":"uses","dst_label":"Postgres",
  "replace":true,"attrs":{},"memory_id":null
}
```

### `POST /v1/graph/unrelate`
Close by `edge_id` **or** `src_label`+`relation`+`dst_label`.

### `POST /v1/graph/neighbors`
`{label, relation?, direction:out|in|both, kind?, at?, limit?}`.

### `POST /v1/graph/path`
Bounded BFS: `{src_label, dst_label, max_hops?, relation?, …}`.

### `POST /v1/graph/subgraph`
`{label, hops:1..3, kind?, at?, limit?}`.

### `POST /v1/graph/history`
`{label?|node_id?|edge_id?, kind?}` → all valid-time versions.

---

## Admin

### `POST /v1/admin/outbox:drain`
Synchronously process pending outbox events (embeddings + graph). Dev helper; production should run `caas-worker`.

---

## curl cheat sheet

```bash
export BASE=http://127.0.0.1:8080
export H=(-H "X-Verified-Tenant: acme" -H "X-Verified-Subject: alice" \
          -H "X-Verified-Groups: platform" -H "Content-Type: application/json")

curl -sS -X POST "$BASE/v1/memories" "${H[@]}" -d @- <<'JSON'
{"kind":"personal","scope_id":"alice","content":"Prefers bullets","source":"chat"}
JSON

curl -sS -X POST "$BASE/v1/context:retrieve" "${H[@]}" -d @- <<'JSON'
{"query":"bullets","scopes":[["personal","alice"]],"mode":"lexical"}
JSON
```

Full walkthrough: `examples/http/assistants_curl.sh`.
