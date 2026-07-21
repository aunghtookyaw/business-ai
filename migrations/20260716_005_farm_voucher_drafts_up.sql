BEGIN;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_voucher_draft (
  id bigserial PRIMARY KEY,
  sector text NOT NULL CHECK (sector IN ('farm', 'sotephwar')),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'validated', 'previewed', 'submitted')),
  voucher_number text NOT NULL DEFAULT '',
  voucher_date date NOT NULL DEFAULT CURRENT_DATE,
  customer_id integer,
  customer_name text NOT NULL DEFAULT '',
  payment_method text NOT NULL DEFAULT '',
  note text NOT NULL DEFAULT '',
  amount_received numeric(18,2) NOT NULL DEFAULT 0,
  lines jsonb NOT NULL DEFAULT '[]'::jsonb,
  total_amount numeric(18,2) NOT NULL DEFAULT 0,
  submitted_transaction_id integer,
  version integer NOT NULL DEFAULT 1,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  CHECK (amount_received >= 0),
  CHECK (total_amount >= 0)
);

CREATE INDEX IF NOT EXISTS business_os_voucher_draft_status_idx
  ON pipkgfu2wr9qxyy.business_os_voucher_draft (sector, status, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS business_os_voucher_draft_submitted_tx_idx
  ON pipkgfu2wr9qxyy.business_os_voucher_draft (submitted_transaction_id)
  WHERE submitted_transaction_id IS NOT NULL;

COMMIT;
