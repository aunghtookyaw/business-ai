-- Read-only checks to run before synchronizing the NocoDB base.
-- This script does not touch NocoDB metadata or the legacy farm_production object.

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'pipkgfu2wr9qxyy'
  AND table_name IN (
    'veggies_crop_master',
    'veggies_crop_alias',
    'veggies_production_imports',
    'veggies_production_batches',
    'veggies_production_items'
  )
ORDER BY table_name;

SELECT tc.table_name, kcu.column_name, ccu.table_name AS referenced_table,
       ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'pipkgfu2wr9qxyy'
  AND tc.table_name = 'veggies_production_items'
ORDER BY kcu.column_name;
