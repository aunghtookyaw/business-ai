BEGIN;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.veggies_crop_master (
    id BIGSERIAL PRIMARY KEY,
    crop_code TEXT NOT NULL UNIQUE,
    crop_name TEXT NOT NULL UNIQUE,
    crop_name_normalized TEXT NOT NULL UNIQUE,
    default_unit TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.veggies_crop_alias (
    id BIGSERIAL PRIMARY KEY,
    crop_id BIGINT NOT NULL REFERENCES pipkgfu2wr9qxyy.veggies_crop_master(id) ON DELETE CASCADE,
    source_header TEXT NOT NULL,
    source_header_normalized TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.veggies_production_imports (
    id BIGSERIAL PRIMARY KEY,
    import_type TEXT NOT NULL DEFAULT 'veggies_production',
    filename TEXT NOT NULL,
    workbook_name TEXT,
    file_hash CHAR(64) NOT NULL,
    imported_by TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    total_source_rows INTEGER NOT NULL DEFAULT 0,
    accepted_rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0,
    created_batches INTEGER NOT NULL DEFAULT 0,
    created_items INTEGER NOT NULL DEFAULT 0,
    duplicate_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'preview',
    error_summary JSONB NOT NULL DEFAULT '[]'::JSONB,
    CONSTRAINT veggies_production_imports_status_check
      CHECK (status IN ('preview', 'running', 'completed', 'completed_with_errors', 'failed'))
);

CREATE INDEX IF NOT EXISTS veggies_production_imports_file_hash_idx
    ON pipkgfu2wr9qxyy.veggies_production_imports (file_hash, status);

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.veggies_production_batches (
    id BIGSERIAL PRIMARY KEY,
    production_date DATE NOT NULL,
    assignee TEXT,
    note TEXT,
    ai_note TEXT,
    entry_date DATE,
    source_file TEXT,
    source_workbook TEXT,
    import_id BIGINT REFERENCES pipkgfu2wr9qxyy.veggies_production_imports(id) ON DELETE RESTRICT,
    source_row_number INTEGER,
    source_row_hash CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,
    CONSTRAINT veggies_production_batches_import_row_unique UNIQUE (import_id, source_row_number),
    CONSTRAINT veggies_production_batches_source_identity_unique
      UNIQUE (source_file, source_workbook, source_row_number, source_row_hash)
);

CREATE INDEX IF NOT EXISTS veggies_production_batches_date_idx
    ON pipkgfu2wr9qxyy.veggies_production_batches (production_date);

ALTER TABLE pipkgfu2wr9qxyy.veggies_production_batches
    ALTER COLUMN source_row_hash DROP NOT NULL;

CREATE TABLE IF NOT EXISTS pipkgfu2wr9qxyy.veggies_production_items (
    id BIGSERIAL PRIMARY KEY,
    production_batch_id BIGINT NOT NULL
      REFERENCES pipkgfu2wr9qxyy.veggies_production_batches(id) ON DELETE CASCADE,
    crop_id BIGINT NOT NULL REFERENCES pipkgfu2wr9qxyy.veggies_crop_master(id) ON DELETE RESTRICT,
    quantity NUMERIC(18,4) NOT NULL,
    unit TEXT,
    quality_grade TEXT,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT veggies_production_items_quantity_check CHECK (quantity >= 0),
    CONSTRAINT veggies_production_items_batch_crop_unique UNIQUE (production_batch_id, crop_id)
);

CREATE INDEX IF NOT EXISTS veggies_production_items_crop_idx
    ON pipkgfu2wr9qxyy.veggies_production_items (crop_id);

INSERT INTO pipkgfu2wr9qxyy.veggies_crop_master
    (crop_code, crop_name, crop_name_normalized, default_unit, active, display_order)
VALUES
    ('ZUCCHINI', 'Zucchini', 'zucchini', NULL, TRUE, 10),
    ('CHERRY_TOMATO', 'Cherry Tomato', 'cherry tomato', NULL, TRUE, 20),
    ('ROSEMARY', 'Rosemary', 'rosemary', NULL, TRUE, 30),
    ('ROMAINE', 'Romaine', 'romaine', NULL, TRUE, 40),
    ('ICEBERG_LETTUCE', 'Iceberg Lettuce', 'iceberg lettuce', NULL, TRUE, 50),
    ('GREEN_OAK_LETTUCE', 'Green Oak Lettuce', 'green oak lettuce', NULL, TRUE, 60),
    ('RED_OAK_LETTUCE', 'Red Oak Lettuce', 'red oak lettuce', NULL, TRUE, 70),
    ('GREEN_LOLLO_LETTUCE', 'Green Lollo Lettuce', 'green lollo lettuce', NULL, TRUE, 80),
    ('RED_LOLLO_LETTUCE', 'Red Lollo Lettuce', 'red lollo lettuce', NULL, TRUE, 90),
    ('DAIKON', 'Daikon', 'daikon', NULL, TRUE, 100),
    ('LEEK', 'Leek', 'leek', NULL, TRUE, 110),
    ('LONG_CHILI', 'Long Chili', 'long chili', NULL, TRUE, 120),
    ('BELL_PEPPER', 'Bell Pepper', 'bell pepper', NULL, TRUE, 130),
    ('RED_CABBAGE', 'Red Cabbage', 'red cabbage', NULL, TRUE, 140),
    ('JAPANESE_CUCUMBER', 'Japanese Cucumber', 'japanese cucumber', NULL, TRUE, 150),
    ('BEETROOT', 'Beetroot', 'beetroot', NULL, TRUE, 160),
    ('CARROT', 'Carrot', 'carrot', NULL, TRUE, 170),
    ('EDAMAME', 'Edamame', 'edamame', NULL, TRUE, 180),
    ('SWISS_CHARD', 'Swiss Chard', 'swiss chard', NULL, TRUE, 190),
    ('ROCKET', 'Rocket', 'rocket', NULL, TRUE, 200),
    ('PARSLEY', 'Parsley', 'parsley', NULL, TRUE, 210),
    ('KALE', 'Kale', 'kale', NULL, TRUE, 220),
    ('RED_RADISH', 'Red Radish', 'red radish', NULL, TRUE, 230),
    ('JAPANESE_PUMPKIN', 'Japanese Pumpkin', 'japanese pumpkin', NULL, TRUE, 240),
    ('THYME', 'Thyme', 'thyme', NULL, TRUE, 250),
    ('GREEN_PERILLA', 'Green Perilla', 'green perilla', NULL, TRUE, 260),
    ('LONG_SWEET_PEPPER', 'Long Sweet Pepper', 'long sweet pepper', NULL, TRUE, 270),
    ('FANCY_TOMATO', 'Fancy Tomato', 'fancy tomato', NULL, TRUE, 280),
    ('ASPARAGUS', 'Asparagus', 'asparagus', NULL, TRUE, 290),
    ('BRUSSELS_SPROUTS', 'Brussels Sprouts', 'brussels sprouts', NULL, TRUE, 300),
    ('BASIL', 'Basil', 'basil', NULL, TRUE, 310),
    ('FENNEL_BULB', 'Fennel Bulb', 'fennel bulb', NULL, TRUE, 320)
ON CONFLICT (crop_code) DO NOTHING;

INSERT INTO pipkgfu2wr9qxyy.veggies_crop_alias
    (crop_id, source_header, source_header_normalized)
SELECT crop.id, aliases.source_header, aliases.source_header_normalized
FROM (VALUES
    ('ZUCCHINI', 'Zucchini', 'zucchini'),
    ('CHERRY_TOMATO', 'Cherry Tomato', 'cherry tomato'),
    ('ROSEMARY', 'Rosemary', 'rosemary'),
    ('ROMAINE', 'Romaine', 'romaine'),
    ('ICEBERG_LETTUCE', 'Iceberg', 'iceberg'),
    ('GREEN_OAK_LETTUCE', 'Green Oak', 'green oak'),
    ('RED_OAK_LETTUCE', 'Red Oak', 'red oak'),
    ('GREEN_LOLLO_LETTUCE', 'Green lollo', 'green lollo'),
    ('RED_LOLLO_LETTUCE', 'Red lollo', 'red lollo'),
    ('DAIKON', 'Daikon', 'daikon'),
    ('LEEK', 'Leek', 'leek'),
    ('LONG_CHILI', 'Long Chilli', 'long chilli'),
    ('BELL_PEPPER', 'Bell Pepper', 'bell pepper'),
    ('RED_CABBAGE', 'Red Cabbage', 'red cabbage'),
    ('JAPANESE_CUCUMBER', 'Japanese Cucumber', 'japanese cucumber'),
    ('BEETROOT', 'Beet root', 'beet root'),
    ('CARROT', 'Carrot', 'carrot'),
    ('EDAMAME', 'Edamame', 'edamame'),
    ('SWISS_CHARD', 'Swiss Chert', 'swiss chert'),
    ('ROCKET', 'Rocket', 'rocket'),
    ('PARSLEY', 'Persley', 'persley'),
    ('KALE', 'Kale', 'kale'),
    ('RED_RADISH', 'Red Radish', 'red radish'),
    ('JAPANESE_PUMPKIN', 'Japanese Pumpkin', 'japanese pumpkin'),
    ('THYME', 'Thyme', 'thyme'),
    ('GREEN_PERILLA', 'Green Perilla', 'green perilla'),
    ('LONG_SWEET_PEPPER', 'Long Sweet Pepper', 'long sweet pepper'),
    ('FANCY_TOMATO', 'Fancy Tomato', 'fancy tomato'),
    ('ASPARAGUS', 'Asparagus', 'asparagus'),
    ('BRUSSELS_SPROUTS', 'Brussel Sprout', 'brussel sprout'),
    ('BASIL', 'Basil', 'basil'),
    ('FENNEL_BULB', 'Funnel Bulb', 'funnel bulb')
) AS aliases(crop_code, source_header, source_header_normalized)
JOIN pipkgfu2wr9qxyy.veggies_crop_master crop USING (crop_code)
ON CONFLICT (source_header_normalized) DO UPDATE SET
    crop_id = EXCLUDED.crop_id,
    source_header = EXCLUDED.source_header;

CREATE OR REPLACE VIEW pipkgfu2wr9qxyy.veggies_production_daily_summary AS
SELECT
    batch.production_date,
    SUM(item.quantity) AS total_quantity,
    COUNT(DISTINCT item.crop_id) AS number_of_crops,
    batch.assignee
FROM pipkgfu2wr9qxyy.veggies_production_batches batch
JOIN pipkgfu2wr9qxyy.veggies_production_items item
  ON item.production_batch_id = batch.id
GROUP BY batch.production_date, batch.assignee;

CREATE OR REPLACE VIEW pipkgfu2wr9qxyy.veggies_production_crop_summary AS
SELECT
    crop.crop_name,
    SUM(item.quantity) AS total_quantity,
    COUNT(DISTINCT batch.production_date) AS number_of_production_days,
    MAX(batch.production_date) AS latest_production_date
FROM pipkgfu2wr9qxyy.veggies_production_items item
JOIN pipkgfu2wr9qxyy.veggies_production_batches batch
  ON batch.id = item.production_batch_id
JOIN pipkgfu2wr9qxyy.veggies_crop_master crop
  ON crop.id = item.crop_id
GROUP BY crop.id, crop.crop_name;

COMMIT;
