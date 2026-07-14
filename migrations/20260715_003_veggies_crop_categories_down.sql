ALTER TABLE pipkgfu2wr9qxyy.veggies_crop_master
  DROP CONSTRAINT IF EXISTS veggies_crop_master_category_check;

ALTER TABLE pipkgfu2wr9qxyy.veggies_crop_master
  DROP COLUMN IF EXISTS category;
