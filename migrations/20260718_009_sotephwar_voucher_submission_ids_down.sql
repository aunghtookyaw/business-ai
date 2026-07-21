BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_submitted_ids_array,
  DROP COLUMN IF EXISTS submitted_transaction_ids;

COMMIT;
