BEGIN;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD COLUMN IF NOT EXISTS submitted_voucher jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS submitted_pdf_path text,
  ADD COLUMN IF NOT EXISTS submitted_pdf_checksum text;

ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP CONSTRAINT IF EXISTS business_os_voucher_draft_submitted_voucher_object;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  ADD CONSTRAINT business_os_voucher_draft_submitted_voucher_object
  CHECK (jsonb_typeof(submitted_voucher) = 'object');

COMMIT;
