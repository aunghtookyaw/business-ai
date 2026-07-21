BEGIN;

DROP INDEX IF EXISTS pipkgfu2wr9qxyy.business_os_customer_submission_customer_idx;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.business_os_customer_submission;
DROP INDEX IF EXISTS pipkgfu2wr9qxyy.customer_master_business_os_group_active_idx;
DROP INDEX IF EXISTS pipkgfu2wr9qxyy.customer_master_business_os_phone_idx;
DROP INDEX IF EXISTS pipkgfu2wr9qxyy.customer_master_business_os_name_idx;
ALTER TABLE pipkgfu2wr9qxyy.customer_master
  DROP COLUMN IF EXISTS business_os_modified_by,
  DROP COLUMN IF EXISTS business_os_modified_at,
  DROP COLUMN IF EXISTS business_os_version;

COMMIT;
