# BigShot Business Dashboard — Phase 1 Prototype

Milestone 1 is served by the read-only dashboard service:

```bash
python3 scripts/dashboard_server.py
```

Then open `http://127.0.0.1:5062`.

Milestone 1 boundaries:

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
