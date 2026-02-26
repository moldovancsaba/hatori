-- 0001_init.sql
-- Hatori PKS: Postgres + pgvector baseline schema
-- Assumes Postgres 13+ recommended.

BEGIN;

-- pgvector extension (requires pgvector installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enumerations
DO $$ BEGIN
  CREATE TYPE pks_module AS ENUM ('A','B','C','D','E','F','G','H','I','J');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE pks_status AS ENUM ('Pending','Approved','Deprecated','Contested');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE pks_provenance AS ENUM ('User','LocalDoc','Web','Tool','Inference');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE pks_confidence AS ENUM ('High','Medium','Low');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE pks_sensitivity AS ENUM ('Public','Private','Restricted');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE refresh_cadence AS ENUM ('None','7d','30d','90d','Custom');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Core PKS records (A–H primarily, but usable for all)
CREATE TABLE IF NOT EXISTS pks_records (
  id              uuid PRIMARY KEY,
  module          pks_module NOT NULL,
  title           text NOT NULL,
  body            text NOT NULL,
  tags            text[] NOT NULL DEFAULT ARRAY[]::text[],
  status          pks_status NOT NULL DEFAULT 'Approved'::pks_status,
  provenance      pks_provenance NOT NULL,
  confidence      pks_confidence NOT NULL,
  scope           text NOT NULL DEFAULT 'Personal',
  sensitivity     pks_sensitivity NOT NULL DEFAULT 'Private'::pks_sensitivity,
  refresh_cadence refresh_cadence NOT NULL DEFAULT 'None'::refresh_cadence,
  refresh_due_at  timestamptz NULL,
  source_refs     text[] NOT NULL DEFAULT ARRAY[]::text[],
  conflict_of     uuid NULL REFERENCES pks_records(id) ON DELETE SET NULL,
  checksum        text NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pks_records_module ON pks_records(module);
CREATE INDEX IF NOT EXISTS idx_pks_records_status ON pks_records(status);
CREATE INDEX IF NOT EXISTS idx_pks_records_updated_at ON pks_records(updated_at);

-- Artefacts registry (local files and/or URLs)
CREATE TABLE IF NOT EXISTS artefacts (
  id          uuid PRIMARY KEY,
  kind        text NOT NULL, -- file|url|note|transcript|export|import
  uri         text NOT NULL, -- filepath or URL
  title       text NULL,
  media_type  text NULL,
  sha256      text NULL,
  metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_artefacts_kind ON artefacts(kind);
CREATE INDEX IF NOT EXISTS idx_artefacts_uri ON artefacts(uri);

-- Interaction events (Module I): append-only log
CREATE TABLE IF NOT EXISTS interaction_events (
  id          uuid PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  session_id  text NULL,
  role        text NOT NULL, -- user|agent|system|tool
  content     text NOT NULL,
  metadata    jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_interaction_events_occurred_at ON interaction_events(occurred_at);

-- Learning events (Module J): append-only feedback signals
CREATE TABLE IF NOT EXISTS learning_events (
  id          uuid PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  kind        text NOT NULL, -- NegativeFeedback|PositiveFeedback|ImplicitPositive|RuleChange|TemplateAdopted
  confidence  pks_confidence NOT NULL DEFAULT 'Low'::pks_confidence,
  details     jsonb NOT NULL DEFAULT '{}'::jsonb,
  related_interaction_id uuid NULL REFERENCES interaction_events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_learning_events_occurred_at ON learning_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_learning_events_kind ON learning_events(kind);

-- Audit events: append-only (memory edits, migrations, model swaps)
CREATE TABLE IF NOT EXISTS audit_events (
  id          uuid PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor       text NOT NULL, -- user|agent|system
  action      text NOT NULL, -- approve|deprecate|redact|migrate|model_swap|config_change
  target_type text NOT NULL, -- pks_record|artefact|schema|model|config
  target_id   text NULL,
  details     jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_events_occurred_at ON audit_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);

-- Embeddings table: store chunks + vector (pgvector)
-- NOTE: choose embedding dimension later; keep column nullable for now.
CREATE TABLE IF NOT EXISTS embeddings (
  id          uuid PRIMARY KEY,
  artefact_id uuid NULL REFERENCES artefacts(id) ON DELETE SET NULL,
  record_id   uuid NULL REFERENCES pks_records(id) ON DELETE SET NULL,
  chunk_id    text NOT NULL,
  content     text NOT NULL,
  embedding   vector NULL,
  metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_embeddings_record_id ON embeddings(record_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_artefact_id ON embeddings(artefact_id);

COMMIT;
