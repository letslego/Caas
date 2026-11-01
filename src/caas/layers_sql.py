"""Shared DDL for profile / episodic / knowledge / operational planes."""

SQLITE_LAYERS = """
CREATE TABLE IF NOT EXISTS profile_facts(
  tenant TEXT NOT NULL, subject TEXT NOT NULL, key TEXT NOT NULL,
  type TEXT NOT NULL, value TEXT NOT NULL, revision INTEGER NOT NULL,
  updated_at TEXT NOT NULL, PRIMARY KEY(tenant, subject, key));
CREATE TABLE IF NOT EXISTS profile_revisions(
  tenant TEXT NOT NULL, subject TEXT NOT NULL, revision INTEGER NOT NULL,
  PRIMARY KEY(tenant, subject));
CREATE TABLE IF NOT EXISTS episodes(
  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
  kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL,
  at TEXT NOT NULL, attrs TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_episodes_subj ON episodes(tenant, subject, at);
CREATE TABLE IF NOT EXISTS knowledge_documents(
  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, title TEXT NOT NULL,
  source TEXT NOT NULL, visibility TEXT NOT NULL, owner TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_chunks(
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL, tenant TEXT NOT NULL,
  ordinal INTEGER NOT NULL, content TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON knowledge_chunks(tenant, document_id);
CREATE TABLE IF NOT EXISTS control_caps(
  tenant TEXT NOT NULL, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
  max_steps INTEGER, max_spend_micros INTEGER, steps INTEGER NOT NULL DEFAULT 0,
  spend_micros INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant, scope, scope_id));
CREATE TABLE IF NOT EXISTS kill_switches(
  tenant TEXT NOT NULL PRIMARY KEY, engaged INTEGER NOT NULL, reason TEXT NOT NULL,
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL);
"""

POSTGRES_LAYERS = """
CREATE TABLE IF NOT EXISTS profile_facts (
  tenant TEXT NOT NULL, subject TEXT NOT NULL, key TEXT NOT NULL,
  type TEXT NOT NULL, value TEXT NOT NULL, revision INTEGER NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (tenant, subject, key));
CREATE TABLE IF NOT EXISTS profile_revisions (
  tenant TEXT NOT NULL, subject TEXT NOT NULL, revision INTEGER NOT NULL,
  PRIMARY KEY (tenant, subject));
CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
  kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL, attrs TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_episodes_subj ON episodes (tenant, subject, at DESC);
CREATE TABLE IF NOT EXISTS knowledge_documents (
  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, title TEXT NOT NULL,
  source TEXT NOT NULL, visibility TEXT NOT NULL, owner TEXT,
  created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  tenant TEXT NOT NULL, ordinal INTEGER NOT NULL, content TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON knowledge_chunks (tenant, document_id);
CREATE TABLE IF NOT EXISTS control_caps (
  tenant TEXT NOT NULL, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
  max_steps INTEGER, max_spend_micros INTEGER,
  steps INTEGER NOT NULL DEFAULT 0, spend_micros INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant, scope, scope_id));
CREATE TABLE IF NOT EXISTS kill_switches (
  tenant TEXT PRIMARY KEY, engaged BOOLEAN NOT NULL, reason TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL, updated_by TEXT NOT NULL);

ALTER TABLE profile_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE control_caps ENABLE ROW LEVEL SECURITY;
ALTER TABLE kill_switches ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_profile_facts') THEN
    CREATE POLICY caas_tenant_profile_facts ON profile_facts
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_profile_revisions') THEN
    CREATE POLICY caas_tenant_profile_revisions ON profile_revisions
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_episodes') THEN
    CREATE POLICY caas_tenant_episodes ON episodes
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_knowledge_documents') THEN
    CREATE POLICY caas_tenant_knowledge_documents ON knowledge_documents
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_knowledge_chunks') THEN
    CREATE POLICY caas_tenant_knowledge_chunks ON knowledge_chunks
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_caps') THEN
    CREATE POLICY caas_tenant_caps ON control_caps
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='caas_tenant_kill') THEN
    CREATE POLICY caas_tenant_kill ON kill_switches
      USING (tenant = current_setting('caas.tenant', true));
  END IF;
END $$;
"""
