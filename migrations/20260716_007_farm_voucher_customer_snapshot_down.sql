BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_customer_snapshot_object;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP COLUMN IF EXISTS customer_snapshot;

COMMIT;
