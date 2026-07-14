ALTER TABLE public.veggies_production_batches
  ADD COLUMN IF NOT EXISTS submission_token UUID;

CREATE UNIQUE INDEX IF NOT EXISTS veggies_production_batches_submission_token_uidx
  ON public.veggies_production_batches (submission_token)
  WHERE submission_token IS NOT NULL;

UPDATE public.veggies_crop_master
SET crop_name = 'Romaine Lettuce', crop_name_normalized = 'romaine lettuce', updated_at = NOW()
WHERE crop_code = 'ROMAINE' AND crop_name = 'Romaine';

INSERT INTO public.veggies_crop_alias (crop_id, source_header, source_header_normalized)
SELECT id, 'Romaine Lettuce', 'romaine lettuce'
FROM public.veggies_crop_master
WHERE crop_code = 'ROMAINE'
ON CONFLICT (source_header_normalized) DO NOTHING;
