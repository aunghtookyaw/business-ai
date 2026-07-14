ALTER TABLE public.veggies_crop_master
  DROP CONSTRAINT IF EXISTS veggies_crop_master_category_check;

ALTER TABLE public.veggies_crop_master
  DROP COLUMN IF EXISTS category;
