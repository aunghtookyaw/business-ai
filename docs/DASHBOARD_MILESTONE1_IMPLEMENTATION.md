# BigShot Business Dashboard — Milestone 1 Implementation Report

Date: June 25, 2026  
Status: Implemented and running  
URL: `http://127.0.0.1:5062`

## Executive Summary

Milestone 1 delivers the Executive Dashboard as the read-only management landing
page. It consumes canonical Business Intelligence functions through a new thin
Business API adapter. Browser components contain no SQL, database connection,
KPI formula, ranking formula, receivable formula, or profit calculation.

Implemented:

- global year, month, week and date-range filters;
- sector, business unit, customer, category, product, location and payment
  status filters;
- revenue, expenses, net profit, cash received and outstanding receivables;
- explicit unavailable state for inventory value;
- revenue, expense, profit, cash-flow and outstanding trends;
- top customers, products and expense categories;
- recent payments and transactions;
- asynchronous Qwen executive narrative;
- PDF and Excel exports through existing renderers;
- dark/light theme, desktop, laptop and tablet layouts;
- local saved-view state;
- launchd deployment and automatic recovery.

Pages scheduled for later milestones remain clearly labelled placeholders.

## Architecture

```text
Browser presentation components
        |
        | JSON filter intent
        v
dashboard_server.py — read-only HTTP boundary
        |
        v
dashboard_service.py — orchestration and 30-second cache
        |
        +--> kpi_overview
        +--> sales_total
        +--> cash_flow
        +--> payment_receive_summary
        +--> top_income
        +--> top_expense_categories
        +--> sotephwar_product_ranking
        +--> recent_payment_receipts
        +--> list_transactions
        +--> sotephwar_inventory_stock
        |
        v
Canonical BI engine → PostgreSQL
```

Qwen receives a restricted subset of calculated BI evidence. Its response is
rejected if it contains a number, amount, percentage, currency name or currency
symbol. Numeric presentation remains deterministic.

## API Endpoints Used

| Method | Endpoint | Engine dependency |
|---|---|---|
| GET | `/api/dashboard/dimensions` | BI search and dashboard dimensions |
| POST | `/api/dashboard/executive` | Canonical functions listed above |
| POST | `/api/dashboard/insights/executive` | Canonical dataset + Qwen narrative |
| POST | `/api/dashboard/export/pdf` | Existing chart PDF renderer |
| POST | `/api/dashboard/export/excel` | Existing BI Excel renderer |

All POST endpoints are read-only filtered queries.

## Filter Semantics

- Year, month, week and range are converted to existing BI period formats.
- Sector and business unit map to canonical sector filters.
- Customer applies to attributable sales, receipts and receivables.
- Customer expenses and profit are explicitly unavailable because costs are not
  attributed to customers.
- Category applies to categorized transaction data.
- Product and location apply to Sote Phwar product/inventory widgets.
- Payment status applies to receivable and recent-payment widgets.
- Unsupported cross-domain combinations return a visible data-quality note.

## BI Validation

2026 Executive Dashboard and direct BI results:

| Metric | Dashboard | Canonical BI | Match |
|---|---:|---:|---|
| Revenue | 3,748,439,670 | 3,748,439,670 | Yes |
| Expenses | 2,077,486,915 | 2,077,486,915 | Yes |
| Net profit | 1,670,952,755 | 1,670,952,755 | Yes |
| Cash received | 1,951,962,170 | 1,951,962,170 | Yes |
| Outstanding | 1,796,477,500 | 1,796,477,500 | Yes |
| Profit margin | 44.58% | 44.58% | Yes |

Parity also passed for:

- June 2026 Sote Phwar;
- June 2026 Farm business unit;
- Mya Yadanar customer scope for attributable metrics.

During validation, `payment_receive_summary` was found to group by voucher number
only. It was corrected to the canonical identity of sector, voucher number,
invoice date and customer. No accounting row was modified.

Product variants such as `1L` and `1 L` are normalized in the BI engine before
ranking. This logic is not present in the dashboard.

## Performance

| Operation | Result |
|---|---:|
| Landing HTML | 0.010 s |
| Executive API cold | 0.36–0.46 s |
| Executive API warm cache | <0.001 s |
| Filter dimensions | 0.061 s |
| Excel export | 0.127 s |
| PDF export | 0.153 s |
| Dashboard process RSS | approximately 37 MB |
| Qwen narrative cold | approximately 47–67 s |
| Qwen narrative cached | approximately 0.002 s |

Qwen is requested separately after calculated widgets render, so AI latency
does not block management figures. The narrative cache is ten minutes; the
Executive data cache is thirty seconds.

## Security

- bound to `127.0.0.1:5062`;
- read-only endpoint allowlist;
- no CORS wildcard;
- no payment/import/edit/delete route;
- no secrets in browser source;
- Content Security Policy and anti-framing headers;
- browser source test rejects SQL and database drivers;
- launchd `KeepAlive`;
- API filter validation and conflict rejection.

## Validation

- 249 automated tests pass;
- Python and JavaScript syntax checks pass;
- PDF and Excel exports are non-empty;
- launchd service health returns HTTP 200;
- canonical parity passed across multiple filter scopes;
- desktop and tablet screenshots captured from live API data.

## Screenshots

- [Desktop Executive Dashboard](../reports/dashboard_milestone1/screenshots/executive-desktop.png)
- [Tablet Executive Dashboard](../reports/dashboard_milestone1/screenshots/executive-tablet.png)

## Known Boundaries

- Inventory value remains unavailable until unit-cost data exists.
- Customer profitability is unavailable until expenses can be attributed to
  customers.
- Qwen may be slow on first generation; calculated widgets remain usable.
- PDF/Excel exports currently focus on the filtered KPI summary. Rich dashboard
  export layout remains Milestone 4.
- Payment and Inventory dashboards remain Milestone 2.
