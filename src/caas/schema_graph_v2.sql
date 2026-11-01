-- Temporal property graph v2: versioned nodes/edges (valid-time).
-- Applied by caas.postgres.ensure_temporal_graph() when upgrading from v1.

ALTER TABLE IF EXISTS graph_edges DROP CONSTRAINT IF EXISTS graph_edges_src_fkey;
ALTER TABLE IF EXISTS graph_edges DROP CONSTRAINT IF EXISTS graph_edges_dst_fkey;

CREATE TABLE IF NOT EXISTS graph_node_ids (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rebuild nodes if still on v1 (no version column).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='public' AND table_name='graph_nodes'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='graph_nodes' AND column_name='version'
  ) THEN
    ALTER TABLE graph_nodes RENAME TO graph_nodes_v1_legacy;
    ALTER TABLE graph_edges RENAME TO graph_edges_v1_legacy;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS graph_nodes (
  tenant TEXT NOT NULL,
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  memory_id TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant, id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_nodes_current_id
  ON graph_nodes (tenant, id) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_nodes_tenant_label_v2
  ON graph_nodes (tenant, lower(label));
CREATE INDEX IF NOT EXISTS idx_graph_nodes_asof
  ON graph_nodes (tenant, id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS graph_edges (
  tenant TEXT NOT NULL,
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  relation TEXT NOT NULL,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  memory_id TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant, id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_edges_current_id
  ON graph_edges (tenant, id) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_edges_src_v2
  ON graph_edges (tenant, src) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_edges_dst_v2
  ON graph_edges (tenant, dst) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_edges_rel_v2
  ON graph_edges (tenant, relation) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_graph_edges_asof
  ON graph_edges (tenant, src, dst, relation, valid_from, valid_to);

-- Copy legacy rows once, then drop legacy tables.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='public' AND table_name='graph_nodes_v1_legacy'
  ) THEN
    INSERT INTO graph_node_ids (id, tenant)
      SELECT id, tenant FROM graph_nodes_v1_legacy
      ON CONFLICT DO NOTHING;
    INSERT INTO graph_nodes
      (tenant, id, version, label, kind, attrs, valid_from, valid_to, memory_id, created_at)
      SELECT tenant, id, 1, label, kind, attrs, valid_from, valid_to, memory_id, created_at
      FROM graph_nodes_v1_legacy
      ON CONFLICT DO NOTHING;
    INSERT INTO graph_edges
      (tenant, id, version, src, dst, relation, attrs, valid_from, valid_to, memory_id, created_at)
      SELECT tenant, id, 1, src, dst, relation, attrs, valid_from, valid_to, memory_id, created_at
      FROM graph_edges_v1_legacy
      ON CONFLICT DO NOTHING;
    DROP TABLE graph_edges_v1_legacy;
    DROP TABLE graph_nodes_v1_legacy;
  END IF;
END $$;

ALTER TABLE graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_node_ids ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_nodes') THEN
    CREATE POLICY caas_tenant_nodes ON graph_nodes
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_edges') THEN
    CREATE POLICY caas_tenant_edges ON graph_edges
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'caas_tenant_node_ids') THEN
    CREATE POLICY caas_tenant_node_ids ON graph_node_ids
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
END $$;
