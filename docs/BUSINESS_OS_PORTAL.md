# BigShot Business OS Portal

## Purpose

BigShot Business OS is the local browser workspace for daily operational tools. It places Receive Payment Basic and Veggies Production Basic inside one navigation shell while preserving their existing business rules and database writes.

This local portal is separate from the public DigitalOcean executive dashboard.

## Start and open

From the repository root:

```bash
python3 ops/business_os_server.py
```

Open `http://127.0.0.1:5059/business-os`.

The server binds to `127.0.0.1` by default. Current access behavior is preserved; unified authentication is a future security sprint. Do not expose this service publicly without a separate security review.

## Architecture

Waitress runs only from the canonical Business OS server entrypoint. Modules continue using the existing Formula Engine database connection helper; the portal does not duplicate database credentials or connections.

- `ops/business_os_server.py`: sole Waitress production entrypoint and `/status` route
- `business_os_app.py`: shared Flask application and Receive Payment business logic
- `tools/veggies_production_portal.py`: Veggies Production routes, validation, queries, and writes
- `tools/business_os_portal.py`: shared shell, route aliases, health display, placeholders, and safe error pages
- `static/business_os.css`: shared responsive presentation
- `static/business_os.js`: accessible small-screen sidebar control
- `dashboard-prototype/assets/bigshot-logo.jpg`: existing official logo displayed by the shell

No database migration or new business table is required.

## Route map

| Route | Purpose |
|---|---|
| `/` | Redirects to Business OS |
| `/business-os` | Local module dashboard |
| `/business-os/farm-voucher` | Integrated Farm Voucher |
| `/business-os/sotephwar-voucher` | Integrated SotePhwar Voucher |
| `/business-os/general-transaction` | General non-voucher Income and Expense workflow |
| `/business-os/sotephwar-inventory` | Integrated SotePhwar Inventory operations |
| `/business-os/receive-payment` | Integrated Receive Payment |
| `/business-os/veggies-production` | Integrated production entry and search |
| `/business-os/veggies-production/crops` | Integrated crop master |
| `/business-os/customers` | Future-module placeholder |
| `/business-os/inventory` | Future-module placeholder |
| `/business-os/financial` | Future-module placeholder |
| `/business-os/reports` | Future-module placeholder |
| `/business-os/settings` | System information and future-module placeholder |

The standalone Receive Payment portal routes are retired. Receive Payment is available only at `/business-os/receive-payment`. Veggies Production record detail and edit paths are available under `/business-os/veggies-production/...`.

## Module integration

Receive Payment retains its voucher lookup, validation, save workflow, and Formula Engine calls. Veggies Production retains category grouping, dynamic crops, blank-versus-zero handling, preview, search, summaries, pagination, details, and confirmed editing. The shared portal wraps their HTML only on integrated routes and rewrites internal module links to keep users inside the shell.

## Adding a future module

1. Keep business queries and validation in a dedicated module.
2. Register routes on the existing Flask application.
3. Add integrated aliases and navigation in `tools/business_os_portal.py`.
4. Use `render_shell` for new pages.
5. Add route, failure, compatibility, and no-secret tests.
6. Do not duplicate the database helper or put credentials in templates.

## Beginner troubleshooting

### Blank page

Run the start command in a terminal and keep it open. Confirm `http://127.0.0.1:5059/status` returns JSON, then reload `/business-os`. Check the terminal for a locally logged exception. Browser users never receive a stack trace.

### PostgreSQL unavailable

The home page reports `Unavailable` without exposing connection details. Confirm PostgreSQL is running and check the existing `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` environment/config values. Do not print secrets. Test the existing database connection before changing application code.

### Where to begin reading

Start at `ops/business_os_server.py`, then read `business_os_app.py` and `tools/business_os_portal.py`. Read `tools/veggies_production_portal.py` for production behavior. Tests in `tests/test_business_os_portal.py`, `tests/test_receive_payment_server.py`, and `tests/test_veggies_production_portal.py` provide small usage examples.

## Protected boundaries

Do not modify `farm_production`, financial transaction semantics, Formula Engine calculations, dashboard proxy/VPS architecture, Nginx, reverse SSH, PostgreSQL exposure, WordPress, Telegram Bot behavior, or NocoDB metadata as part of portal presentation work.
