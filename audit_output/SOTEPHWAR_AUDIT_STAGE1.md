# SotePhwar Transaction Data Audit — Stage 1

This audit was executed with a PostgreSQL `READ ONLY`, `REPEATABLE READ` transaction. The Excel workbook was opened in read-only mode. No workbook or production record was modified.

## Summary

- Excel row count: 858
- Database active sales row count: 890
- Exact matches: 266
- Product-normalized matches: 361
- Customer-normalized matches: 24
- Quantity mismatches: 2
- Amount mismatches: 8
- Excel-only rows: 4
- Database-only rows: 3
- Newer Business OS records: 0
- Ambiguous rows: 155
- Probable duplicates: 38
- Proposed customer aliases: 28
- Product aliases: 7
- Payment discrepancies: 96
- Excel date range: 2025-01-19 to 2027-07-11
- Database date range: 2025-01-19 to 2027-07-11

## Database Profile

- Unique voucher numbers: 237
- Blank linked/fallback customer names: 24
- Duplicate-looking active sales rows: 46
- Distinct product spellings: 7

## Payment Comparison

- `excel_amount_received_missing`: 175
- `matches_original_database_received_not_current`: 202
- `payment_discrepancy`: 96
- `payment_match`: 82

Current received follows the canonical helper semantics: the larger of materialized `Total_Received` and cumulative linked `Payment_Receive`; outstanding and status are then derived with the canonical balance/status helper.

## Safety Verification

| Table | Before | After | Identical |
|---|---:|---:|---:|
| `Sotephwar_Transection` | 890 | 890 | yes |
| `Payment_Receive` | 353 | 353 | yes |
| `Sotephwar_Inventory` | 33 | 33 | yes |

Overall protected-table count verification: **PASS**.

## Matching Limitations

- Matching uses normalized invoice number, invoice date, customer, and product; quantity and total amount are comparison fields.
- Repeated voucher numbers are valid when they represent different product lines.
- Multiple rows sharing the same full normalized key are not force-matched.
- Customer normalization is deterministic and limited to spacing, commas, and the supported Daw/Ma/U/Ko suffix-to-prefix forms; no fuzzy customer merging is used.
- `newer_business_os_record` means the database invoice date is later than the maximum Excel invoice date.
- Payment rows with missing invoice dates or non-identical normalized customer identities are not silently attached to a voucher.
- If multiple Excel line rows contain the same received value for one voucher, it is treated as a repeated voucher-level value; differing values are summed and flagged through the aggregation-method column.

## Unresolved Mappings

- None.
