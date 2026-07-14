DELETE FROM public.veggies_crop_alias
WHERE source_header_normalized = 'romaine lettuce';

UPDATE public.veggies_crop_master
SET crop_name = 'Romaine', crop_name_normalized = 'romaine', updated_at = NOW()
WHERE crop_code = 'ROMAINE' AND crop_name = 'Romaine Lettuce';

DROP INDEX IF EXISTS public.veggies_production_batches_submission_token_uidx;

ALTER TABLE public.veggies_production_batches
  DROP COLUMN IF EXISTS submission_token;
