BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_submitted_voucher_object,
  DROP COLUMN IF EXISTS submitted_pdf_checksum,
  DROP COLUMN IF EXISTS submitted_pdf_path,
  DROP COLUMN IF EXISTS submitted_voucher;

COMMIT;
