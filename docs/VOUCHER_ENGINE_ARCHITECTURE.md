# Shared Voucher Engine

## Workflow

`Draft → Validate → Preview → Print/PDF → Submit → Transaction table`

The first implemented domain is Farm. `tools/voucher_engine.py` owns shared,
side-effect-free validation and preview totals. Farm-specific mapping converts a
validated voucher into the existing aggregate `farm_transection` row semantics;
line detail remains in Voucher Engine storage for preview/print. Farm drafts use
chronologically sorted Delivery Date sections while retaining one header Invoice
Date and one aggregate payment identity. Each item stores either an active Crop
Master ID or a custom description, never both. Sote Phwar
will reuse the workflow and add its own adapter.

Farm customer selection reads the canonical NocoDB-backed
`pipkgfu2wr9qxyy.customer_master` directly and only offers active Farm/Both
records. The selected name, phone, town, address, payment terms, group and active
state are copied to `business_os_voucher_draft.customer_snapshot`. Preview and
print use that immutable draft snapshot; submission retains the existing
Customer Master relationship and does not add detail columns to
`farm_transection`.

## Safety boundaries

- Draft, validation, preview and print are non-mutating.
- Submit must run all line inserts, Customer Master links and draft status change
  in one PostgreSQL transaction.
- Submit must reject a duplicate canonical voucher identity while holding a
  transaction-scoped advisory lock.
- Preview totals and submitted totals must come from the same Decimal calculation.
- The existing Formula Engine remains the reporting source of truth.
- The Executive Dashboard remains read-only and has no voucher mutation routes.
- Production credentials never enter browser code or draft JSON.

## Next adapter work

1. Confirm exact Farm transaction column names and required NocoDB metadata.
2. Add server-side draft storage and authenticated CRUD routes.
3. Add Farm app UI for line entry, validation, preview and print/PDF.
4. Add atomic submit repository with idempotency key and audit record.
5. Reuse the workflow for Sote Phwar field definitions and transaction mapping.
