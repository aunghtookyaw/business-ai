# Excel Business Data Import

This folder contains an append-only Excel import workflow for:

- `Transection`
- `Farm_Transection`
- `Sotephwar_Transection`
- `Financial_Obligations`
- `Sotephwar_Inventory`
- `Veggies Production` (wide Excel input normalized into `veggies_*` tables)

The importer inserts new rows into Postgres/NocoDB tables. It does not delete, update, truncate, replace, or clear existing data.

The Veggies Production browser workflow, template, validation rules, and command-line
dry run are documented in [`../docs/FARM_PRODUCTION_SYSTEM.md`](../docs/FARM_PRODUCTION_SYSTEM.md).

## Files

- `business_data_import_template.xlsx`: workbook template with the input sheets.
- `BusinessDataImport.bas`: Excel VBA macro module for the upload button.

## Setup In Excel For Mac

1. Open `business_data_import_template.xlsx`.
2. Save it as `business_data_import_template.xlsm`.
3. Open Excel's VBA editor.
4. Import `BusinessDataImport.bas`.
5. Optional: add a button on the `Instructions` sheet and assign it to `UploadBusinessData`.

## Upload

Start the local import server:

```bash
cd /Users/bigshot/ai-automation/business-ai
python3 scripts/excel_import_server.py
```

Fill rows in Excel, then run the `UploadBusinessData` macro or click your assigned button.

Rows with blank `Upload_Status` are uploaded. After a successful insert, the macro marks the row `INSERTED` and records the inserted table id, so clicking again skips those rows.

## Airtable CSV Daily Import

Put the daily Airtable exports on the Desktop with these names:

- `June farm.csv`
- `June sotephwar.csv`

Convert them into the `Transection` sheet:

```bash
cd /Users/bigshot/ai-automation/business-ai
python3 scripts/import_airtable_transactions.py
```

The converter maps both CSV files into the workbook's exact import format. It
sets `Sector` to `Farm` or `Sote Phwar`, leaves `Upload_Status` blank for new
rows, and skips rows already present in the workbook.

## Farm Transaction Upload

Use the `Farm_Transection` sheet for the separate NocoDB table named
`farm_transection`. Required fields are `Date`, `Customer`, and `Total_Amount`.
The upload command also accepts `Invoice_Number`, `Total_Received`,
`Outstanding_Balance`, `Note`, and `AI_Analysis`. If `Outstanding_Balance` is
blank, the importer calculates `Total_Amount - Total_Received`; if it is filled,
it must match that formula.
