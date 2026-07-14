# BigShot Veggies Production System

## Purpose

The Veggies Production system records daily vegetable quantities without changing the legacy `farm_production` NocoDB view or `farm_transection` business logic. Staff use a wide Excel sheet or the simplified NocoDB entry table; PostgreSQL stores normalized batches and crop items.

Start here if you are new to the code:

1. `tools/veggies_production.py` contains date parsing, aliases, validation, normalization, duplicate detection, and database insertion.
2. `scripts/excel_import_server.py` exposes the Business Data Import page and endpoints.
3. `migrations/20260714_001_veggies_production_up.sql` defines the database.
4. `scripts/import_veggies_production.py` provides command-line preview and import.
5. `scripts/create_veggies_production_template.py` generates the staff workbook from active crops.

## Architecture

```text
Wide Excel row
    |
    +--> preview and row validation
    |
    +--> veggies_production_batches (one source row)
            |
            +--> veggies_production_items (one entered crop quantity)
                    |
                    +--> veggies_crop_master

Import audit --> veggies_production_imports
Old headers  --> veggies_crop_alias --> veggies_crop_master
```

The existing `farm_production` object is independent and must not be renamed, modified, deleted, or migrated.

## Database Schema

All objects are in the configured `TRANSACTION_SCHEMA`, currently `pipkgfu2wr9qxyy`.

### `veggies_crop_master`

Stores stable crop codes and standardized display names. `default_unit` is nullable because no production unit was verified. A new crop is added here rather than by altering production tables.

### `veggies_crop_alias`

Maps normalized historical workbook headers to standardized crops. Source spelling is retained in `source_header`.

### `veggies_production_imports`

Records filename, workbook/sheet name, SHA-256 file hash, source/accepted/rejected counts, created batch/item counts, duplicates, status, errors, operator, and timestamps.

### `veggies_production_batches`

One record per source submission. It stores the production date, assignee, notes, entry date, import/source identity, row hash, and audit timestamps. Multiple submissions may share a production date. Source identity is optional for manual NocoDB entry.

### `veggies_production_items`

One record per entered crop quantity. The `(production_batch_id, crop_id)` constraint prevents the same crop appearing twice in one batch. Quantity is decimal and must be zero or greater.

### Read-only SQL views

- `veggies_production_daily_summary`
- `veggies_production_crop_summary`

These are future reporting entry points and do not alter Formula Engine behavior.

## NocoDB Configuration

The NocoDB base is `AI Business OS`. Keep the existing `farm_production` view unchanged.

Only these new tables should be visible to normal users:

- `veggies_production_batches`, titled **Veggies Production Entry**
- `veggies_crop_master`, titled **Veggies Crop Master**

Keep these implementation objects hidden from the normal menu where supported:

- `veggies_production_items`
- `veggies_production_imports`
- `veggies_crop_alias`
- both summary views

The batch-to-item and item-to-crop foreign keys should be synchronized as linked records. Production items remain available through the batch relation even when their technical table is hidden from the top-level menu.

Do not edit NocoDB PostgreSQL metadata tables manually. Use the NocoDB metadata synchronization UI/API with a valid administrator token.

Offline preparation artifacts:

- `nocodb/veggies_production_metadata.json` is the declarative visibility, title, field, and relationship plan.
- `nocodb/veggies_production_verify.sql` verifies the source tables and foreign keys without changing data.
- `scripts/configure_nocodb_veggies.py` prints the plan by default and can read live metadata with `--inspect-live`. It never mutates NocoDB.

After logging in as a NocoDB administrator:

1. Run the verification SQL against PostgreSQL.
2. Synchronize the `pipkgfu2wr9qxyy` schema in the **AI Business OS** base.
3. Rename `veggies_production_batches` to **Veggies Production Entry**.
4. Rename `veggies_crop_master` to **Veggies Crop Master**.
5. Confirm both foreign-key relationships from `veggies_production_items` were detected.
6. Hide every object listed in `hidden_tables` from normal users.
7. Do not rename, hide, resynchronize destructively, or otherwise edit `farm_production` or `farm_transection`.

## Business Data Import Workflow

Start the local service:

```bash
python3 scripts/excel_import_server.py
```

Open `http://127.0.0.1:5055` and:

1. Select **Veggies Production**.
2. Download the template.
3. Upload a completed `.xlsx` workbook.
4. Review source, accepted, rejected, item, and duplicate counts.
5. Download rejected-row errors when present.
6. Confirm the import.

The existing JSON and Excel macro import endpoints remain unchanged.

Command-line dry run:

```bash
python3 scripts/import_veggies_production.py "/path/to/workbook.xlsx" --json
```

Explicit import after review:

```bash
python3 scripts/import_veggies_production.py "/path/to/workbook.xlsx" --apply --imported-by "operator-name"
```

## Template Columns

The wide `Data Entry` sheet contains Production Date, one column for each active crop, Assignee, Note, AI Note, and Date of Entry. Instructions and Crop Master reference sheets are also included. Crop quantities accept decimals and reject negatives. The preferred date display is `YYYY/MM/DD`.

Generate the template locally after the migration is available:

```bash
python3 scripts/create_veggies_production_template.py
```

The default output is `excel_import/BigShot_Veggies_Production_Template.xlsx`. The generator queries active crops so newly configured crops appear automatically. Use `--output /path/file.xlsx` to select another destination. Final visual verification is a local operator step.

## Date Handling

Accepted input:

- Excel serial dates using the workbook 1900 date system
- actual Excel date/datetime cells
- `YYYY/MM/DD`
- `YYYY-MM-DD`
- `DD/MM/YYYY`

PostgreSQL stores `production_date` and `entry_date` as `DATE`, never text. Ambiguous month-first text is not accepted.

## Unit Handling

No trustworthy unit was present in the reference workbook or existing operational system. Every seeded crop therefore has `default_unit = NULL`. Do not infer kilograms, pieces, bunches, or trays. Units can be configured later in Veggies Crop Master and copied into future imported items.

## Duplicate Rules

Production date alone is never a duplicate key. Multiple submissions on one day are valid.

Protection layers:

- completed import file hash detection;
- duplicate canonical source-row hashes inside a workbook;
- unique import batch/source-row identity;
- unique source file/workbook/row/hash identity;
- unique batch/crop items.

A repeated completed file returns `already_exists`; it does not overwrite production.

## Blank Versus Zero

- Blank crop cell: no item record is created.
- Explicit `0`: an item record is created with quantity zero.

This preserves confirmed zero production separately from missing/unentered production.

## Crop Alias Mapping

| Historical header | Standard crop |
|---|---|
| Iceberg | Iceberg Lettuce |
| Green Oak | Green Oak Lettuce |
| Red Oak | Red Oak Lettuce |
| Green lollo | Green Lollo Lettuce |
| Red lollo | Red Lollo Lettuce |
| Long Chilli | Long Chili |
| Beet root | Beetroot |
| Swiss Chert | Swiss Chard |
| Persley | Parsley |
| Brussel Sprout | Brussels Sprouts |
| Funnel Bulb | Fennel Bulb |

Exact historical headers for all other seeded crops are also stored in the alias table.

## Validation and Transactions

Every populated source row must have a supported production date, only recognized crop headers, at least one entered crop quantity, numeric quantities greater than or equal to zero, and a valid Date of Entry when supplied.

Errors identify row and column. Invalid rows create neither a batch nor items. Database insertion uses one transaction; a fatal failure rolls back the import.

## Migrations

Apply:

```bash
python3 scripts/migrate_veggies_production.py up
```

Rollback deletes only the new `veggies_*` objects and their data:

```bash
python3 scripts/migrate_veggies_production.py down
```

Never run rollback without confirming backups and intended data loss.

## Tests

Focused tests:

```bash
python3 -B -m unittest tests.test_veggies_production tests.test_excel_import_server tests.test_excel_importer -v
```

Full suite:

```bash
python3 -B -m unittest discover -s tests -v
```

## Backup and Recovery

The pre-migration full PostgreSQL custom archive is:

`backups/veggies_production_pre_migration_20260714_230130/automationdb_pre_veggies_production.dump`

SHA-256: `2c48509d14f9db9680254fa6cdb17e78692fcca07a0597660733905810d0b186`

Validate with `pg_restore -l`. Restore into a separate database first when testing recovery. The reversible migration is the preferred rollback when only the new empty system must be removed.

## Adding a Crop

1. Add a unique code and standardized name to Veggies Crop Master.
2. Leave `default_unit` blank unless the business confirms a unit.
3. Add aliases for any historical or alternate headers.
4. Generate a new template so the active crop becomes a wide entry column.
5. Test an import preview before production use.

No PostgreSQL table alteration is required.

## Troubleshooting

- **Unknown crop header:** add a reviewed alias or correct the header.
- **Invalid date:** use an Excel date or a supported unambiguous format.
- **No crop quantities:** enter at least one crop; zero is acceptable.
- **Already exists:** the completed file hash has already been imported.
- **NocoDB table missing:** synchronize metadata with a valid NocoDB administrator token; never insert NocoDB metadata rows manually.
- **Template unavailable:** run `python3 scripts/create_veggies_production_template.py` before starting the import service.
- **NocoDB login unavailable:** use the offline metadata and verification files above, then apply the UI changes after an administrator logs in.
