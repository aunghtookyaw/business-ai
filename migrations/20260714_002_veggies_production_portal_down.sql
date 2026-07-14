DELETE FROM pipkgfu2wr9qxyy.veggies_crop_alias
WHERE source_header_normalized = 'romaine lettuce';

UPDATE pipkgfu2wr9qxyy.veggies_crop_master
SET crop_name = 'Romaine', crop_name_normalized = 'romaine', updated_at = NOW()
WHERE crop_code = 'ROMAINE' AND crop_name = 'Romaine Lettuce';

DROP INDEX IF EXISTS pipkgfu2wr9qxyy.veggies_production_batches_submission_token_uidx;

ALTER TABLE pipkgfu2wr9qxyy.veggies_production_batches
  DROP COLUMN IF EXISTS submission_token;
