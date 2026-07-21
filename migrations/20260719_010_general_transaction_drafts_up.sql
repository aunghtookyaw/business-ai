BEGIN;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_general_transaction_draft (
  id bigserial PRIMARY KEY,
  submission_key uuid NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'validated', 'previewed', 'submitted')),
  transaction_date date NOT NULL DEFAULT CURRENT_DATE,
  transaction_type text NOT NULL DEFAULT '',
  sector text NOT NULL DEFAULT '',
  category_id integer,
  description text NOT NULL DEFAULT '',
  amount bigint NOT NULL DEFAULT 0,
  payment_method text NOT NULL DEFAULT '',
  attachment_path text NOT NULL DEFAULT '',
  attachment_name text NOT NULL DEFAULT '',
  comment text NOT NULL DEFAULT '',
  submitted_transaction_id integer,
  submitted_json jsonb,
  version integer NOT NULL DEFAULT 1,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  CHECK (amount >= 0)
);

CREATE INDEX IF NOT EXISTS business_os_general_transaction_draft_status_idx
  ON pipkgfu2wr9qxyy.business_os_general_transaction_draft
  (status, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS business_os_general_transaction_submitted_tx_idx
  ON pipkgfu2wr9qxyy.business_os_general_transaction_draft (submitted_transaction_id)
  WHERE submitted_transaction_id IS NOT NULL;

COMMIT;
