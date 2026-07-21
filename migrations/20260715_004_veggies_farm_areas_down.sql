BEGIN;

ALTER TABLE public.veggies_production_batches
    DROP CONSTRAINT IF EXISTS veggies_production_batches_farm_area_id_fkey;
DROP INDEX IF EXISTS public.veggies_production_batches_farm_area_idx;
ALTER TABLE public.veggies_production_batches
    DROP COLUMN IF EXISTS farm_area_id;
DROP TABLE IF EXISTS public.veggies_farm_area_master;

COMMIT;
