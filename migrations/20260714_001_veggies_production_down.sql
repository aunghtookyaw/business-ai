BEGIN;

DROP VIEW IF EXISTS pipkgfu2wr9qxyy.veggies_production_crop_summary;
DROP VIEW IF EXISTS pipkgfu2wr9qxyy.veggies_production_daily_summary;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.veggies_production_items;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.veggies_production_batches;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.veggies_production_imports;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.veggies_crop_alias;
DROP TABLE IF EXISTS pipkgfu2wr9qxyy.veggies_crop_master;

COMMIT;
