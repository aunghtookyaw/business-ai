ALTER TABLE public.veggies_crop_master
  ADD COLUMN IF NOT EXISTS category TEXT;

UPDATE public.veggies_crop_master
SET category = CASE crop_code
  WHEN 'ROMAINE' THEN 'Leafy Vegetables'
  WHEN 'ICEBERG_LETTUCE' THEN 'Leafy Vegetables'
  WHEN 'GREEN_OAK_LETTUCE' THEN 'Leafy Vegetables'
  WHEN 'RED_OAK_LETTUCE' THEN 'Leafy Vegetables'
  WHEN 'GREEN_LOLLO_LETTUCE' THEN 'Leafy Vegetables'
  WHEN 'RED_LOLLO_LETTUCE' THEN 'Leafy Vegetables'
  WHEN 'SWISS_CHARD' THEN 'Leafy Vegetables'
  WHEN 'ROCKET' THEN 'Leafy Vegetables'
  WHEN 'KALE' THEN 'Leafy Vegetables'
  WHEN 'ZUCCHINI' THEN 'Fruit Vegetables'
  WHEN 'CHERRY_TOMATO' THEN 'Fruit Vegetables'
  WHEN 'LONG_CHILI' THEN 'Fruit Vegetables'
  WHEN 'BELL_PEPPER' THEN 'Fruit Vegetables'
  WHEN 'JAPANESE_CUCUMBER' THEN 'Fruit Vegetables'
  WHEN 'LONG_SWEET_PEPPER' THEN 'Fruit Vegetables'
  WHEN 'FANCY_TOMATO' THEN 'Fruit Vegetables'
  WHEN 'JAPANESE_PUMPKIN' THEN 'Fruit Vegetables'
  WHEN 'DAIKON' THEN 'Root and Bulb Vegetables'
  WHEN 'LEEK' THEN 'Root and Bulb Vegetables'
  WHEN 'RED_CABBAGE' THEN 'Root and Bulb Vegetables'
  WHEN 'BEETROOT' THEN 'Root and Bulb Vegetables'
  WHEN 'CARROT' THEN 'Root and Bulb Vegetables'
  WHEN 'RED_RADISH' THEN 'Root and Bulb Vegetables'
  WHEN 'FENNEL_BULB' THEN 'Root and Bulb Vegetables'
  WHEN 'ROSEMARY' THEN 'Herbs and Specialty Crops'
  WHEN 'PARSLEY' THEN 'Herbs and Specialty Crops'
  WHEN 'THYME' THEN 'Herbs and Specialty Crops'
  WHEN 'GREEN_PERILLA' THEN 'Herbs and Specialty Crops'
  WHEN 'BASIL' THEN 'Herbs and Specialty Crops'
  WHEN 'ASPARAGUS' THEN 'Herbs and Specialty Crops'
  WHEN 'EDAMAME' THEN 'Legumes and Others'
  WHEN 'BRUSSELS_SPROUTS' THEN 'Legumes and Others'
  ELSE 'Other'
END,
updated_at = NOW()
WHERE category IS NULL;

ALTER TABLE public.veggies_crop_master
  ALTER COLUMN category SET DEFAULT 'Other',
  ALTER COLUMN category SET NOT NULL;

ALTER TABLE public.veggies_crop_master
  DROP CONSTRAINT IF EXISTS veggies_crop_master_category_check;

ALTER TABLE public.veggies_crop_master
  ADD CONSTRAINT veggies_crop_master_category_check CHECK (category IN (
    'Leafy Vegetables',
    'Fruit Vegetables',
    'Root and Bulb Vegetables',
    'Herbs and Specialty Crops',
    'Legumes and Others',
    'Other'
  ));
