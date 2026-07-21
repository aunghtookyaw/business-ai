BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
  ADD COLUMN IF NOT EXISTS deleted_by text,
  ADD COLUMN IF NOT EXISTS deletion_reason text,
  ADD COLUMN IF NOT EXISTS deletion_previous_status text;

ALTER TABLE pipkgfu2wr9qxyy.business_os_general_transaction_draft
  ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
  ADD COLUMN IF NOT EXISTS deleted_by text,
  ADD COLUMN IF NOT EXISTS deletion_reason text,
  ADD COLUMN IF NOT EXISTS deletion_previous_status text;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.business_os_inventory_movement_draft (
  id bigserial PRIMARY KEY,
  submission_key uuid NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','validated','previewed','submitted')),
  movement_date date NOT NULL DEFAULT CURRENT_DATE,
  movement_type text NOT NULL DEFAULT '',
  product text NOT NULL DEFAULT '',
  from_store text NOT NULL DEFAULT '',
  to_store text NOT NULL DEFAULT '',
  quantity bigint NOT NULL DEFAULT 0 CHECK (quantity >= 0),
  note text NOT NULL DEFAULT '',
  submitted_movement_id integer,
  submitted_json jsonb,
  version integer NOT NULL DEFAULT 1,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  is_deleted boolean NOT NULL DEFAULT false,
  deleted_at timestamptz,
  deleted_by text,
  deletion_reason text,
  deletion_previous_status text
);

CREATE INDEX IF NOT EXISTS business_os_voucher_active_draft_idx
  ON pipkgfu2wr9qxyy.business_os_voucher_draft (sector,updated_at DESC)
  WHERE is_deleted=false AND status<>'submitted';
CREATE INDEX IF NOT EXISTS business_os_general_active_draft_idx
  ON pipkgfu2wr9qxyy.business_os_general_transaction_draft (updated_at DESC)
  WHERE is_deleted=false AND status<>'submitted';
CREATE INDEX IF NOT EXISTS business_os_inventory_active_draft_idx
  ON pipkgfu2wr9qxyy.business_os_inventory_movement_draft (updated_at DESC)
  WHERE is_deleted=false AND status<>'submitted';
CREATE UNIQUE INDEX IF NOT EXISTS business_os_inventory_submitted_movement_idx
  ON pipkgfu2wr9qxyy.business_os_inventory_movement_draft (submitted_movement_id)
  WHERE submitted_movement_id IS NOT NULL;

COMMIT;
