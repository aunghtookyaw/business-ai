BEGIN;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_data_audit (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  target_key text NOT NULL CHECK (target_key IN ('sotephwar_transection','farm_transection','transection')),
  target_table text NOT NULL,
  filename text NOT NULL,
  sheet_name text,
  source_rows integer NOT NULL DEFAULT 0,
  source_columns integer NOT NULL DEFAULT 0,
  detected_date date,
  headers jsonb NOT NULL DEFAULT '[]'::jsonb,
  column_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
  mapping_confidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_data jsonb NOT NULL DEFAULT '[]'::jsonb,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'uploaded'
    CHECK (status IN ('uploaded','mapping_required','ready','audited','approved','applied','failed','ignored')),
  rows_compared integer NOT NULL DEFAULT 0,
  changes_applied integer NOT NULL DEFAULT 0,
  applied_at timestamptz,
  applied_by text,
  version bigint NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_data_audit_row (
  id bigserial PRIMARY KEY,
  audit_id bigint NOT NULL REFERENCES pipkgfu2wr9qxyy.business_os_data_audit(id) ON DELETE CASCADE,
  excel_row_number integer,
  database_row_id integer,
  classification text NOT NULL,
  match_key jsonb NOT NULL DEFAULT '{}'::jsonb,
  excel_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  normalized_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  database_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  differences jsonb NOT NULL DEFAULT '{}'::jsonb,
  candidate_database_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  decision text NOT NULL DEFAULT 'pending'
    CHECK (decision IN ('pending','accept_excel','accept_database','ignore','merge_alias')),
  decision_note text,
  decided_by text,
  decided_at timestamptz,
  applied boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS business_os_data_audit_created_idx
  ON pipkgfu2wr9qxyy.business_os_data_audit (created_at DESC);
CREATE INDEX IF NOT EXISTS business_os_data_audit_target_idx
  ON pipkgfu2wr9qxyy.business_os_data_audit (target_key, status, created_at DESC);
CREATE INDEX IF NOT EXISTS business_os_data_audit_row_audit_idx
  ON pipkgfu2wr9qxyy.business_os_data_audit_row (audit_id, classification, decision, id);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_data_audit_alias (
  id bigserial PRIMARY KEY,
  alias_type text NOT NULL CHECK (alias_type IN ('customer','product')),
  original_value text NOT NULL,
  normalized_value text NOT NULL,
  normalized_lookup text NOT NULL,
  target_key text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text NOT NULL,
  UNIQUE (alias_type, normalized_lookup, target_key)
);

CREATE INDEX IF NOT EXISTS business_os_data_audit_alias_lookup_idx
  ON pipkgfu2wr9qxyy.business_os_data_audit_alias (alias_type, normalized_lookup)
  WHERE active;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_data_audit_mapping (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  target_key text NOT NULL CHECK (target_key IN ('sotephwar_transection','farm_transection','transection')),
  normalized_headers jsonb NOT NULL,
  column_mapping jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text NOT NULL,
  UNIQUE (target_key, name)
);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_data_audit_backup (
  id bigserial PRIMARY KEY,
  audit_id bigint NOT NULL REFERENCES pipkgfu2wr9qxyy.business_os_data_audit(id),
  audit_row_id bigint NOT NULL REFERENCES pipkgfu2wr9qxyy.business_os_data_audit_row(id),
  target_table text NOT NULL,
  database_row_id integer NOT NULL,
  operation text NOT NULL CHECK (operation IN ('insert','update')),
  before_record jsonb,
  after_record jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL
);

CREATE INDEX IF NOT EXISTS business_os_data_audit_backup_audit_idx
  ON pipkgfu2wr9qxyy.business_os_data_audit_backup (audit_id, id);

COMMIT;
