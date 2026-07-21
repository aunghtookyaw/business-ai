BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD COLUMN IF NOT EXISTS submitted_transaction_ids jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_submitted_ids_array;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD CONSTRAINT business_os_voucher_draft_submitted_ids_array
  CHECK (jsonb_typeof(submitted_transaction_ids) = 'array');

COMMIT;
