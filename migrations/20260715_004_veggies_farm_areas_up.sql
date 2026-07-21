BEGIN;

CREATE TABLE IF NOT EXISTS public.veggies_farm_area_master (
    id BIGSERIAL PRIMARY KEY,
    area_code TEXT NOT NULL UNIQUE,
    area_name TEXT NOT NULL UNIQUE,
    area_name_normalized TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.veggies_farm_area_master
    (area_code, area_name, area_name_normalized, active, display_order)
VALUES
    ('HOME_FARM', 'Home Farm', 'home farm', TRUE, 10),
    ('NORTH_FARM', 'North Farm', 'north farm', TRUE, 20),
    ('SOUTH_FARM', 'South Farm', 'south farm', TRUE, 30),
    ('EAST_FARM', 'East Farm', 'east farm', TRUE, 40),
    ('OTHER', 'Other', 'other', TRUE, 50)
ON CONFLICT (area_code) DO UPDATE SET
    area_name = EXCLUDED.area_name,
    area_name_normalized = EXCLUDED.area_name_normalized,
    active = EXCLUDED.active,
    display_order = EXCLUDED.display_order,
    updated_at = NOW();

ALTER TABLE public.veggies_production_batches
    ADD COLUMN IF NOT EXISTS farm_area_id BIGINT;

UPDATE public.veggies_production_batches
SET farm_area_id = (
    SELECT id FROM public.veggies_farm_area_master WHERE area_code = 'HOME_FARM'
), updated_at = NOW()
WHERE farm_area_id IS NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.veggies_production_batches WHERE farm_area_id IS NULL) THEN
        RAISE EXCEPTION 'Farm Area migration cannot enforce NOT NULL while unassigned batches remain';
    END IF;
END $$;

ALTER TABLE public.veggies_production_batches
    ALTER COLUMN farm_area_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'veggies_production_batches_farm_area_id_fkey'
          AND conrelid = 'public.veggies_production_batches'::regclass
    ) THEN
        ALTER TABLE public.veggies_production_batches
            ADD CONSTRAINT veggies_production_batches_farm_area_id_fkey
            FOREIGN KEY (farm_area_id)
            REFERENCES public.veggies_farm_area_master(id)
            ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS veggies_production_batches_farm_area_idx
    ON public.veggies_production_batches (farm_area_id, production_date);

COMMIT;
