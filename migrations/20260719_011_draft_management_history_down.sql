BEGIN;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.business_os_inventory_movement_draft;
DROP INDEX IF EXISTS pipkgfu2wr9qxyy.business_os_general_active_draft_idx;
DROP INDEX IF EXISTS pipkgfu2wr9qxyy.business_os_voucher_active_draft_idx;
ALTER TABLE pipkgfu2wr9qxyy.business_os_general_transaction_draft
  DROP COLUMN IF EXISTS deletion_previous_status,DROP COLUMN IF EXISTS deletion_reason,
  DROP COLUMN IF EXISTS deleted_by,DROP COLUMN IF EXISTS deleted_at,DROP COLUMN IF EXISTS is_deleted;
ALTER TABLE pipkgfu2wr9qxyy.business_os_voucher_draft
  DROP COLUMN IF EXISTS deletion_previous_status,DROP COLUMN IF EXISTS deletion_reason,
  DROP COLUMN IF EXISTS deleted_by,DROP COLUMN IF EXISTS deleted_at,DROP COLUMN IF EXISTS is_deleted;
COMMIT;
