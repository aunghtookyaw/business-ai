# BigShot Veggies Production System

## Purpose and approved workflow

**Veggies Production Basic is the primary production-entry method.** Staff enter, search, review, and correct daily vegetable production directly in a local browser portal.

The uploaded Excel workbook was only a visual reference for the wide crop layout. Excel upload, preview, confirmation, rejected-row files, and spreadsheet-driven insertion are not part of the approved production workflow.

The system does not rename, modify, delete, or migrate the legacy `farm_production` NocoDB object or `farm_transection` table.

## Beginner entry point

Read these files in order:

1. `tools/veggies_production_portal.py` — browser routes, validation, HTML, search, details, corrections, and transactional database writes.
2. `scripts/receive_payment_server.py` — existing localhost Flask/Waitress service that hosts the portal.
3. `tools/veggies_production.py` — shared crop, quantity, date, and category helpers.
4. `migrations/20260714_001_veggies_production_up.sql` — normalized base schema.
5. `migrations/20260714_002_veggies_production_portal_up.sql` — browser submission token and corrected Romaine Lettuce name.
6. `migrations/20260715_003_veggies_crop_categories_up.sql` — editable categories and safe crop-category seed mapping.

## Start command and URL

Apply migrations:

```bash
python3 scripts/migrate_veggies_production.py up
```

Start the existing local Business OS service:

```bash
python3 scripts/receive_payment_server.py
```

Open:

`http://127.0.0.1:5059/veggies-production`

The server binds to localhost by default. PostgreSQL is never exposed publicly.

## Browser workflow

One submitted form creates:

- one `veggies_production_batches` record;
- one `veggies_production_items` record for every entered crop quantity.

Crop inputs are generated from active `veggies_crop_master` records, so activating a new crop adds it to the browser form without changing page code.

Crops are grouped using these editable categories:

- Leafy Vegetables
- Fruit Vegetables
- Root and Bulb Vegetables
- Herbs and Specialty Crops
- Legumes and Others
- Other

The crop-name search filters fields immediately without reloading. **Entered Crops Only** hides blank fields for review and never changes stored data.

Entry fields:

- Production Date, required
- Assignee, free text
- one decimal-capable quantity input per active crop
- Note
- AI Note
- Date of Entry, defaulted to today

`created_at` records the exact database save time. `entry_date` remains a PostgreSQL `DATE`, consistent with the normalized schema.

Rules:

- Blank quantity: no item record.
- Explicit zero: confirmed-zero item record.
- Decimal: accepted.
- Negative: rejected beside the crop field.
- At least one crop: required.
- Every save: one database transaction.
- Repeated browser submission token: rejected to prevent accidental double insertion.

The create workflow uses Post/Redirect/Get, and JavaScript disables the Save button after submission. The unique database token is the final double-submit safeguard.

The live entry preview shows the production date, assignee, entered-crop count, total entered quantity, and only entered crop lines. Blank inputs are excluded; explicit zero remains visible. Server-side validation remains authoritative.

After saving, the success message shows production date, assignee, crop count, and total saved quantity without exposing an internal record ID.

## Today’s summary calculations

The top cards use batches whose `created_at` falls on PostgreSQL `CURRENT_DATE`, following the existing local database timezone convention:

- Today’s Total Production: sum of quantities saved today.
- Today’s Number of Submissions: distinct batches saved today.
- Today’s Number of Crops Produced: distinct crops saved today.
- Latest Entry Time: latest batch `created_at` today.

Totals never assume or append a unit. **Unit configuration pending** appears when item units are unknown or mixed.

## Search and summaries

Filters:

- Date From
- Date To
- exact Production Date
- Assignee
- Crop
- Minimum Quantity
- Maximum Quantity
- Note text
- Sort: newest, oldest, highest total quantity, or lowest total quantity

Results show production date, assignee, total quantity, crop count, note, entry date, View, and Edit.

Newest first is the default. Results use 25 records per page with Previous and Next controls.

## Detail and safe correction

The detail screen shows batch metadata and each crop, quantity, unit, created time, and updated time.

Editing requires an explicit Edit action. The page shows an original-value summary and requires a Save Changes confirmation checkbox. A transaction locks the batch, updates its editable fields, replaces its normalized items, and updates `updated_at`. A failure rolls back the entire correction.

The edit warning shows original created time and last updated time. Crop fields use the same category grouping as new entry. If a crop is later deactivated, historical details and edits still display it.

There is no delete action and no permanent-delete workflow.

## Database architecture

All objects use the configured `TRANSACTION_SCHEMA`, currently `pipkgfu2wr9qxyy`.

### `veggies_crop_master`

Standard crop names, codes, editable category, nullable default unit, active status, and display order. The portal reads this table dynamically.

Open `http://127.0.0.1:5059/veggies-production/crops` to edit Crop Name, Category, Active, Default Unit, and Display Order. Deactivate crops instead of deleting them. Historical relationships use stable crop IDs, so corrected names remain linked.

### `veggies_production_batches`

One row per browser submission. Stores production date, assignee, notes, entry date, submission token, timestamps, and optional import compatibility fields.

### `veggies_production_items`

One normalized crop quantity per batch. Quantity must be zero or greater. `(production_batch_id, crop_id)` is unique.

### Compatibility tables

- `veggies_crop_alias`
- `veggies_production_imports`

These remain for compatibility with previously implemented optional utilities. They are not used by normal browser entry.

### Read-only reporting views

- `veggies_production_daily_summary`
- `veggies_production_crop_summary`

They are future reporting entry points and do not change Formula Engine behavior.

## Units

No trustworthy production units were provided. Seeded crops therefore keep `default_unit = NULL`. Do not infer kilograms, pieces, bunches, or trays. A configured crop default unit is copied into newly saved production items.

## NocoDB

The browser portal is the primary entry method. Normal NocoDB users should only see:

- `veggies_production_batches`, titled **Veggies Production Entry**
- `veggies_crop_master`, titled **Veggies Crop Master**

Keep items, imports, aliases, and summary views hidden from normal menus where supported. Relationships still connect items to batches and crops.

Offline configuration artifacts:

- `nocodb/veggies_production_metadata.json`
- `nocodb/veggies_production_verify.sql`
- `scripts/configure_nocodb_veggies.py`

Never edit NocoDB’s PostgreSQL metadata tables directly. Never change the legacy `farm_production` object.

## Excel utility classification

The earlier Veggies workbook parser, preview/import endpoints, CLI dry-run, and template generator are retained as **harmless optional developer utilities**. They do not conflict with normalized storage, so they were not deleted. They are hidden from the main Business Data Import workflow and are not the production-entry method.

Retained files include:

- `scripts/create_veggies_production_template.py`
- `scripts/import_veggies_production.py`
- compatibility endpoints in `scripts/excel_import_server.py`
- workbook parsing helpers in `tools/veggies_production.py`

Do not use these utilities to insert normal production data.

## Migrations and rollback

Apply all Veggies migrations:

```bash
python3 scripts/migrate_veggies_production.py up
```

Rollback is destructive to the new Veggies system and must only be used after confirming the backup:

```bash
python3 scripts/migrate_veggies_production.py down
```

The rollback never targets the legacy farm objects.

## Backup and recovery

Pre-migration custom archive:

`backups/veggies_production_pre_migration_20260714_230130/automationdb_pre_veggies_production.dump`

SHA-256:

`2c48509d14f9db9680254fa6cdb17e78692fcca07a0597660733905810d0b186`

The dump is private and ignored by Git. Validate with `pg_restore -l` and test restoration into a separate database.

Pre-category-migration archive:

`backups/veggies_usability_pre_migration_20260715_000000/automationdb_veggies_schema.dump`

SHA-256:

`5184965ad1424ca6b575701232b665ee23d9e6ebed0e0a52131b77a6b6f10052`

## Tests

Focused portal and existing Receive Payment Basic tests:

```bash
python3 -B -m unittest tests.test_veggies_production_portal tests.test_receive_payment_server -v
```

Full suite:

```bash
python3 -B -m unittest discover -s tests -v
```

## Adding a crop

1. Add a unique code and standardized name in Veggies Crop Master.
2. Leave the default unit blank unless the business confirms it.
3. Set the crop active and assign its display order.
4. Refresh Veggies Production Basic.
5. Test a browser submission and detail view.

No PostgreSQL production-table alteration is required.

## Troubleshooting

- **Portal does not open:** confirm `scripts/receive_payment_server.py` is running, then use the exact localhost URL above.
- **Crop is missing:** confirm it exists and is active in `veggies_crop_master`, then refresh.
- **Crop is in the wrong group:** open Veggies Crop Master, correct its category, save, and refresh.
- **Long crop form:** use Search crop, or select Entered Crops Only after entering quantities.
- **Invalid date:** use the browser date picker.
- **No crop quantities:** enter at least one crop; zero is valid.
- **Already saved:** refresh before creating another submission. The unique token prevented a duplicate.
- **Save or edit failed:** no partial change was committed. Check PostgreSQL connectivity and the Receive Payment service logs, then retry from a fresh page.
- **Search returns nothing:** clear filters, verify the date range, then add filters one at a time.
- **More search results exist:** use Previous and Next below the table; each page contains 25 records.
- **NocoDB table missing:** synchronize the schema after administrator login using the prepared metadata plan; do not manipulate metadata tables directly.
