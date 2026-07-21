BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD COLUMN IF NOT EXISTS customer_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_customer_snapshot_object;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD CONSTRAINT business_os_voucher_draft_customer_snapshot_object
  CHECK (jsonb_typeof(customer_snapshot) = 'object');

COMMIT;
