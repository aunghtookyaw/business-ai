BEGIN;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_metadata_object;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP COLUMN IF EXISTS voucher_metadata;
COMMIT;
