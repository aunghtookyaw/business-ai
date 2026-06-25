# BigShot Business Dashboard v1.0 — Phase 1 Design Definition

Status: Awaiting implementation approval  
Date: June 25, 2026

## 1. Executive Design Position

The dashboard is a read-only presentation layer over the existing Business
Intelligence engine. It must not connect to PostgreSQL, generate SQL, reproduce
formulas, aggregate raw rows, or ask Qwen to calculate business metrics.

```text
Dashboard UI
    |
    v
Read-only Business API adapter
    |
    v
BIIntent / executive tool contracts
    |
    v
Canonical Business Intelligence engine
    |
    v
PostgreSQL
```

Qwen receives validated BI outputs and produces narrative only.

The existing system has stable Python BI contracts but no general dashboard
HTTP API. Phase 2 implementation should add a thin read-only adapter around
`execute_intent()` and approved executive report functions. It must contain no
SQL and no calculation logic.

## 2. Information Architecture

```text
BigShot Dashboard
├── Executive
│   ├── Performance
│   ├── Cash & collections
│   ├── Inventory position
│   ├── Customer concentration
│   └── AI executive brief
├── Payment Analytics
│   ├── Receivables
│   ├── Collection performance
│   ├── Aging
│   └── Payment history
├── Inventory
│   ├── Stock by location
│   ├── Movement
│   ├── Production
│   └── Availability risks
├── Customers
│   ├── Revenue ranking
│   ├── Payment behaviour
│   ├── Outstanding ranking
│   └── Customer history
├── Farm
│   ├── Financial performance
│   ├── Cash flow
│   ├── Customers
│   └── Operations
├── Sote Phwar
│   ├── Sales
│   ├── Production
│   ├── Inventory
│   ├── Dealers
│   └── Receivables
├── Financial
│   ├── Profit and loss
│   ├── Cash flow
│   ├── Revenue and expense mix
│   └── Period comparisons
└── AI Insights
    ├── Executive summary
    ├── Risks
    ├── Opportunities
    ├── Recommendations
    └── Management actions
```

Primary navigation uses eight permanent destinations. A secondary tab layer is
not required for Version 1; section anchors and drill-down drawers are simpler
and preserve context.

## 3. Global Filter Model

The persistent filter bar is the single source of UI state:

- period mode: year, month, week, or date range;
- sector;
- business unit;
- customer;
- category;
- location/store;
- product;
- payment status.

Rules:

1. A filter change creates one immutable filter intent.
2. Every visible widget receives the same intent.
3. Widgets may declare a filter unsupported; they must not silently reinterpret
   it.
4. Refresh invalidates all page widget requests together.
5. Saved views store UI filter and layout state only, never business values.
6. PDF and Excel exports send the same intent to validated report renderers.

## 4. Navigation Structure

Desktop:

- fixed 232-pixel left navigation;
- persistent global filters below the page heading;
- 12-column content grid;
- page-level export and saved-view controls.

Tablet:

- navigation becomes an off-canvas drawer;
- filters remain horizontally scrollable;
- charts and tables stack into full-width panels.

Mobile:

- compact header and navigation drawer;
- two-column KPI cards;
- one content panel per row;
- detail tables use horizontal scrolling;
- exports move to a page action menu in implementation.

## 5. Thirty-Second Executive Hierarchy

The first viewport answers five questions in order:

1. Are revenue and profit healthy?
2. Is cash conversion healthy?
3. How much remains uncollected?
4. Is inventory available?
5. What requires management action today?

The hierarchy is:

```text
Global context
  → six primary KPI cards
  → performance trend
  → AI executive brief
  → cash and collection risk
  → customer, expense and inventory detail
```

Inventory Value must display “Unavailable — unit cost required” until the BI
engine provides a validated value. The dashboard must not estimate it.

Accounts Payable and Balance Sheet follow the same rule: unavailable metrics are
explicitly labelled rather than inferred from reminder or transaction data.

## 6. Component Map

| Component | Responsibility | Business logic permitted |
|---|---|---|
| AppShell | Navigation, theme, responsive layout | None |
| GlobalFilterBar | Build and publish filter intent | Date/UI validation only |
| PageHeader | Title, context, export actions | None |
| MetricCard | Render value, comparison and state | Formatting only |
| TrendChart | Render supplied series | Axis/visual scaling only |
| BreakdownChart | Render supplied categories | Visual scaling only |
| DataTable | Sort/page supplied rows | Presentation sorting only |
| StatusBadge | Render supplied status | None |
| InsightPanel | Render Qwen narrative sections | None |
| DataQualityState | Explain unavailable/incomplete data | None |
| ExportMenu | Request BI PDF/Excel output | None |
| SavedViewControl | Persist UI state | None |
| ErrorBoundary | Show API failure and retry | None |
| LoadingSkeleton | Show request state | None |

Client-side sorting is acceptable for already returned rows. Client-side totals,
percentages, rankings, aging buckets, profit, cash flow, collection rate and
growth calculations are prohibited.

## 7. API Dependency Map

Proposed API routes are adapter contracts, not implemented endpoints.

| UI dependency | Proposed read-only route | Existing engine source |
|---|---|---|
| Filter options | `GET /api/dashboard/dimensions` | BI search/master-data helpers |
| KPI cards | `POST /api/dashboard/widgets/kpi` | `execute_intent(... report=kpi)` |
| Revenue | `POST /api/dashboard/widgets/revenue` | `sales_total` through BI executor |
| Expenses | `POST /api/dashboard/widgets/expense` | `expense_total` through BI executor |
| Cash flow | `POST /api/dashboard/widgets/cash-flow` | `cash_flow` through BI executor |
| Top customers | `POST /api/dashboard/widgets/top-customers` | `top_income` through BI executor |
| Customer history | `POST /api/dashboard/widgets/customer-history` | `sotephwar_transection_customer` |
| Outstanding | `POST /api/dashboard/widgets/outstanding` | approved receivables/customer report |
| Inventory stock | `POST /api/dashboard/widgets/inventory-stock` | `sotephwar_inventory_stock` |
| Inventory movement | `POST /api/dashboard/widgets/inventory-movement` | movement summary/list |
| Expense categories | `POST /api/dashboard/widgets/expense-categories` | `category_summary` |
| Comparison | `POST /api/dashboard/widgets/comparison` | executive comparison tool |
| Executive narrative | `POST /api/dashboard/insights/executive` | executive tools + Qwen narrative |
| PDF export | `POST /api/dashboard/export/pdf` | existing PDF renderers |
| Excel export | `POST /api/dashboard/export/excel` | existing Excel renderers |

All POST routes above are read-only query requests. Use POST because the filter
intent is structured and may contain arrays and date ranges.

Required request envelope:

```json
{
  "filters": {
    "period": {"type": "year", "year": 2026},
    "sector": "",
    "business_unit": "",
    "customer": "",
    "category": "",
    "location": "",
    "product": "",
    "payment_status": ""
  },
  "widget": {"limit": 10}
}
```

Required response envelope:

```json
{
  "ok": true,
  "generated_at": "2026-06-25T22:00:00+06:30",
  "filter_label": "2026 · All sectors",
  "data": {},
  "data_quality": [],
  "source": {"engine": "bi_executor", "formula": "kpi_overview"}
}
```

The `source` metadata is mandatory for auditability. It identifies an existing
engine contract, not SQL.

## 8. Widget Inventory and Readiness

### Executive

| Widget | Readiness |
|---|---|
| Revenue, expenses, net profit, cash received, outstanding | Ready |
| Collection rate, profit margin, cash flow | Ready |
| Revenue/expense growth | Ready through comparison contract |
| Inventory units and location | Ready |
| Inventory value | Blocked by unit cost data |
| Accounts payable | Requires approved payable model |
| Revenue, expense, profit and cash trends | Needs time-series API composition in BI layer |
| Collection and outstanding trends | Needs time-series BI contract |
| Top customers and expenses | Ready |
| Top products | Current engine supports product detail, not ranked product list |
| Recent payments | Needs read-only payment-history BI report contract |
| Recent transactions | Ready |

### Payment Analytics

Outstanding, payment history, status and collection totals are available.
Reliable customer aging by invoice due date requires due-date semantics; current
aging should not be promoted without confirming its business definition.

### Inventory

Stock and movement are ready. Value, turnover, fast/slow moving, near stock-out
and dead stock need validated cost, reorder threshold and aging contracts in the
BI engine before display.

### Customer

Revenue ranking, payment history and outstanding ranking are ready. Customer
growth requires a time-series customer contract. Lifetime value remains future.

### Farm

Revenue, expenses, profit and cash flow are ready. Crop performance and Farm
inventory require confirmation of canonical operational sources.

### Sote Phwar

Sales, production, revenue, profit, inventory, outstanding and dealer/customer
performance have canonical sources.

### Financial

Profit and loss, cash flow, period comparison, revenue and expense breakdown are
ready. Balance sheet remains future.

### AI Insights

Executive summary, risk, opportunity and recommendation narratives are ready.
Forecast and anomaly detection remain future.

## 9. User Roles

Version 1 uses read-only role-based views:

| Role | Default page | Scope |
|---|---|---|
| CEO | Executive | All business units and AI brief |
| CFO / Finance | Financial | All financial, payment and customer data |
| Farm Manager | Farm | Farm financial and operational scope |
| Factory Manager | Sote Phwar | Production, inventory and sales scope |
| Sales / Collection Manager | Payments | Customers, receivables and payment history |
| Management Viewer | Executive | Authorized read-only scope |

Roles affect available scope and default page, not calculations.

## 10. Visual System

### Color palette

| Token | Light | Purpose |
|---|---|---|
| Forest 900 | `#174F3B` | Brand, primary actions |
| Forest 600 | `#26775A` | Revenue, positive trends |
| Sage 100 | `#E4F0EA` | Selected states, subtle panels |
| Charcoal | `#17211C` | Primary text |
| Stone | `#69756F` | Secondary text |
| Canvas | `#F3F5F4` | Application background |
| White | `#FFFFFF` | Panels |
| Gold | `#B28A42` | Attention, comparison |
| Red | `#B64B49` | Risk, negative cash |

Color never carries meaning alone. Every state also uses labels or icons.

### Typography

- UI/data: Inter or system sans-serif;
- executive headings and large numeric emphasis: Georgia;
- base size: 14 pixels;
- table and metadata minimum: 11 pixels desktop, 10 pixels compact;
- tabular figures should use consistent digit widths in implementation.

### Density

- 8-pixel spacing scale;
- 16-pixel panel radius;
- restrained shadows;
- six primary cards at desktop width;
- one dominant chart per viewport;
- muted decoration and high data-to-ink ratio.

## 11. Wireframes

### Desktop

```text
┌──────────┬────────────────────────────────────────────────────────────┐
│ Sidebar  │ Page title                    Export  Save  Theme          │
│          ├────────────────────────────────────────────────────────────┤
│ Executive│ Global period and dimension filters                       │
│ Payments ├────────────────────────────────────────────────────────────┤
│ Inventory│ KPI  KPI  KPI  KPI  KPI  KPI                              │
│ Customers├──────────────────────────────────────┬─────────────────────┤
│ Farm     │ Revenue / expense / profit trend     │ AI executive brief  │
│ Sote     ├───────────────┬──────────────────────┼─────────────────────┤
│ Finance  │ Cash flow     │ Collections          │ Inventory location  │
│ AI       ├──────────────────────────────────────┼─────────────────────┤
│          │ Top customers                       │ Expense categories  │
└──────────┴──────────────────────────────────────┴─────────────────────┘
```

### Tablet

```text
┌───────────────────────────────────────────────┐
│ Menu  Page title                       Theme  │
├───────────────────────────────────────────────┤
│ Scrollable global filters                     │
├───────────────────────────────────────────────┤
│ KPI KPI KPI                                   │
│ KPI KPI KPI                                   │
├───────────────────────────────────────────────┤
│ Primary chart                                 │
├───────────────────────────────────────────────┤
│ AI brief                                      │
├───────────────────────────────────────────────┤
│ Supporting panels and tables                  │
└───────────────────────────────────────────────┘
```

### Mobile

```text
┌───────────────────────┐
│ Menu  BIGSHOT   Theme │
├───────────────────────┤
│ Page title            │
│ Period filters →      │
├───────────┬───────────┤
│ KPI       │ KPI       │
│ KPI       │ KPI       │
├───────────────────────┤
│ Primary chart         │
├───────────────────────┤
│ AI brief              │
├───────────────────────┤
│ Table → horizontal    │
└───────────────────────┘
```

## 12. Interaction Requirements

- filter changes show a debounced loading state;
- all widgets expose last-updated time and source metadata;
- failed widgets retry independently without clearing successful widgets;
- unavailable metrics show data requirements;
- chart selection opens a detail drawer using the same filter intent;
- exports retain current filters and visible business scope;
- dark mode changes presentation only;
- keyboard navigation and visible focus states are mandatory;
- motion respects `prefers-reduced-motion`.

## 13. Security and Operational Boundaries

- dashboard service binds to localhost unless a separate authenticated network
  deployment is approved;
- no edit, delete, payment or import endpoints are available to the dashboard;
- API allowlist contains dashboard read contracts only;
- secrets remain server-side;
- responses exclude database credentials and raw SQL;
- saved views contain no business data;
- all API requests are logged with role, scope, widget and duration;
- Qwen prompts exclude secrets and receive only necessary calculated outputs.

## 14. Implementation Approval Gates

Implementation should begin only after approval of:

1. navigation and page scope;
2. Executive Dashboard visual direction;
3. global filter semantics;
4. metric availability labels;
5. proposed read-only API adapter;
6. role scope;
7. visual palette and typography;
8. Version 1 exclusions.

Version 1 exclusions recommended:

- balance sheet;
- inventory value and turnover;
- dead/slow/fast-moving inventory;
- customer lifetime value;
- forecast;
- anomaly detection;
- any write operation.

## 15. Prototype

The clickable prototype is in `dashboard-prototype/index.html`.

It includes:

- detailed Executive Dashboard visual direction;
- all eight navigation destinations;
- global filter interaction;
- expandable secondary filters;
- desktop, tablet and mobile responsive behavior;
- light/dark mode;
- presentation-only export and save-view feedback;
- explicit non-production data labelling.

No production API, SQL, calculation or service was added.
