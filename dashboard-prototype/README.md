# BigShot Business Dashboard — Phase 1 Prototype

Milestone 1 is served by the read-only dashboard service:

```bash
export MASTER_USERNAME=your-master-user
export MASTER_PASSWORD=your-master-password
export DASHBOARD_COOKIE_SECURE=0
python3 scripts/dashboard_server.py
```

Then open `http://127.0.0.1:5062`.

Production deployment targets Docker behind the Nginx HTTPS reverse proxy for
`dashboard.bigshotagribusiness.com`:

```bash
cp deploy/dashboard.env.example .env.dashboard
docker compose -f deploy/docker-compose.dashboard.yml up -d --build
```

Set real `MASTER_USERNAME`, `MASTER_PASSWORD`, and `DASHBOARD_SECRET_KEY` in
`.env.dashboard`. Do not commit that file.

Milestone 1 boundaries:

- dashboard pages require login before any dashboard data is loaded;
- master credentials come from environment variables only;
- no registration or public users;
- future role names are exposed as metadata but not active yet;
- browser components contain no database connection or SQL;
- API calls are read-only;
- no KPI calculations;
- no editing or deletion;
- Executive values come from `tools.dashboard_service`;
- all eight navigation destinations are clickable;
- only the Executive page is implemented;
- remaining pages stay milestone placeholders.

The implementation API contract is documented in
`docs/BUSINESS_DASHBOARD_V1_PHASE1.md`.
