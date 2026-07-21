BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD COLUMN IF NOT EXISTS voucher_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_metadata_object;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD CONSTRAINT business_os_voucher_draft_metadata_object
  CHECK (jsonb_typeof(voucher_metadata) = 'object');

COMMIT;
