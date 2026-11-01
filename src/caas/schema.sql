-- CaaS PostgreSQL + pgvector schema (reference). Apply via caas.postgres.migrate().
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS scopes (
  tenant TEXT NOT NULL,
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  owner TEXT NOT NULL,
  classification TEXT NOT NULL,
  PRIMARY KEY (tenant, kind, id)
);

CREATE TABLE IF NOT EXISTS grants (
  tenant TEXT NOT NULL,
  kind TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  subject TEXT NOT NULL,
  permission TEXT NOT NULL,
  PRIMARY KEY (tenant, kind, scope_id, subject, permission)
);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  kind TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  content TEXT NOT NULL,
  source TEXT NOT NULL,
  memory_type TEXT NOT NULL,
  classification TEXT NOT NULL,
  purpose TEXT NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  origin_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_scope
  ON memories (tenant, kind, scope_id, status);
CREATE INDEX IF NOT EXISTS idx_memories_purpose
  ON memories (tenant, purpose, status);

CREATE TABLE IF NOT EXISTS revisions (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL,
  actor TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS audit (
  at TIMESTAMPTZ NOT NULL,
  tenant TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  resource TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_at ON audit (tenant, at DESC);

-- Durable outbox for asynchronous vector/graph projection.
CREATE TABLE IF NOT EXISTS outbox (
  id BIGSERIAL PRIMARY KEY,
  tenant TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox (id) WHERE processed_at IS NULL;

-- Vector projection (separate from source-of-truth memories).
CREATE TABLE IF NOT EXISTS memory_embeddings (
  memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
  tenant TEXT NOT NULL,
  kind TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  classification TEXT NOT NULL,
  status TEXT NOT NULL,
  model TEXT NOT NULL,
  embedding vector(384) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_scope
  ON memory_embeddings (tenant, kind, scope_id, purpose, status);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_hnsw
  ON memory_embeddings USING hnsw (embedding vector_cosine_ops);

-- Temporal property graph (valid-time intervals; valid_to NULL = current).
CREATE TABLE IF NOT EXISTS graph_nodes (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  memory_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_tenant_label
  ON graph_nodes (tenant, lower(label));
CREATE INDEX IF NOT EXISTS idx_graph_nodes_current
  ON graph_nodes (tenant, kind) WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS graph_edges (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  src TEXT NOT NULL REFERENCES graph_nodes(id),
  dst TEXT NOT NULL REFERENCES graph_nodes(id),
  relation TEXT NOT NULL,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  memory_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges (tenant, src) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_edges_dst ON graph_edges (tenant, dst) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_edges_rel ON graph_edges (tenant, relation) WHERE valid_to IS NULL;

-- Tenant RLS helpers. Application sets: SELECT set_config('caas.tenant', $1, true);
ALTER TABLE scopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_scopes') THEN
    CREATE POLICY caas_tenant_scopes ON scopes
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_grants') THEN
    CREATE POLICY caas_tenant_grants ON grants
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_memories') THEN
    CREATE POLICY caas_tenant_memories ON memories
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_audit') THEN
    CREATE POLICY caas_tenant_audit ON audit
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_outbox') THEN
    CREATE POLICY caas_tenant_outbox ON outbox
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_embeddings') THEN
    CREATE POLICY caas_tenant_embeddings ON memory_embeddings
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_nodes') THEN
    CREATE POLICY caas_tenant_nodes ON graph_nodes
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_edges') THEN
    CREATE POLICY caas_tenant_edges ON graph_edges
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
END $$;

-- Table owners bypass RLS unless FORCE ROW LEVEL SECURITY is applied for the
-- non-owner app role used in real deployments. The reference demo sets
-- caas.tenant per transaction and still filters by tenant in SQL.
