BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.customer_master
  ADD COLUMN IF NOT EXISTS business_os_version bigint NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS business_os_modified_at timestamptz,
  ADD COLUMN IF NOT EXISTS business_os_modified_by text;

CREATE INDEX IF NOT EXISTS customer_master_business_os_name_idx
  ON pipkgfu2wr9qxyy.customer_master (lower(btrim(customer_name)));
CREATE INDEX IF NOT EXISTS customer_master_business_os_phone_idx
  ON pipkgfu2wr9qxyy.customer_master (phone_number text_pattern_ops);
CREATE INDEX IF NOT EXISTS customer_master_business_os_group_active_idx
  ON pipkgfu2wr9qxyy.customer_master (customer_group, active);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_customer_submission (
  id bigserial PRIMARY KEY,
  submission_key uuid NOT NULL UNIQUE,
  action text NOT NULL CHECK (action IN ('create', 'update', 'status')),
  customer_id integer REFERENCES pipkgfu2wr9qxyy.customer_master(id),
  request_hash text NOT NULL,
  response_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS business_os_customer_submission_customer_idx
  ON pipkgfu2wr9qxyy.business_os_customer_submission (customer_id, created_at DESC);

COMMIT;
