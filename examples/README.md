# CaaS examples

Runnable samples for **personal**, **team**, and **organization** assistants: write durable memory, read scoped context, and (on Postgres) project vectors/graph edges.

## Quick start (in-process)

```bash
pip install -e '.[dev]'
python examples/personal_assistant.py
python examples/team_assistant.py
python examples/organization_assistant.py
python examples/assistants_promotion_flow.py
```

With PostgreSQL + pgvector:

```bash
docker compose up -d postgres
export CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas
pip install -e '.[dev,postgres]'
python examples/personal_assistant.py
python examples/team_assistant.py
python examples/organization_assistant.py
python examples/assistants_promotion_flow.py
python examples/postgres_demo.py
```

## HTTP samples

```bash
CAAS_UNSAFE_DEV_HEADERS=1 caas-api --host 127.0.0.1 --port 8080
bash examples/http/assistants_curl.sh
```

SDK against a live API: `python examples/sdk_mcp_demo.py`

## What each sample shows

| Sample | Write | Read | Isolation / governance |
|---|---|---|---|
| `personal_assistant.py` | preferences + open actions | owner retrieve | peer cannot read/write; revise |
| `team_assistant.py` | decisions + schedule; optional promote | group-granted retrieve | non-member denied; graph edges |
| `organization_assistant.py` | confidential policies | clearance-aware retrieve | vendor denied; multi-scope retrieve |
| `assistants_promotion_flow.py` | personal → team → org | cross-scope context | promotion copies, no source mutate |
| `http/assistants_curl.sh` | same via REST | same via REST | header identity (dev only) |
| `assemble_demo.py` | working+profile+durable+episodes+knowledge | budgeted `assemble()` pack | timings_ms / NFR-oriented |

## Docs

- [Documentation index](../docs/INDEX.md)
- [Architecture layers](../docs/ARCHITECTURE.md)
- [REST API reference](../docs/API.md)
- [SDK + MCP](../docs/SDK.md)
