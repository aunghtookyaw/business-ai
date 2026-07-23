# BigShot AI Business OS — Production Runbook

## Health Checks

```bash
curl http://127.0.0.1:5059/health
curl http://127.0.0.1:5062/health
curl http://127.0.0.1:8080/api/v1/health
curl http://127.0.0.1:11434/api/tags
docker compose ps
```

Expected network exposure:

- PostgreSQL: `127.0.0.1:5433`
- NocoDB: `127.0.0.1:8080`
- Receive Payment: `127.0.0.1:5059`
- Business Dashboard: `127.0.0.1:5062`
- Ollama: local runtime on `127.0.0.1:11434`

## Deployment

```bash
cd /Users/bigshot/ai-automation
docker compose config --quiet
docker compose up -d

cd /Users/bigshot/ai-automation/business-ai
python3 -m unittest discover -s tests
python3 -m py_compile telegram_bot.py business_agent.py business_os_app.py ops/business_os_server.py tools/formula_engine.py
launchctl kickstart -k gui/$(id -u)/com.bigshot.business-ai.telegram-bot
launchctl kickstart -k gui/$(id -u)/com.bigshot.businessos
launchctl kickstart -k gui/$(id -u)/com.bigshot.business-dashboard
```

Run the health checks after every deployment. Do not deploy when the regression
suite fails or when the database backup cannot be listed by `pg_restore -l`.

## Logs

- Finance bot stdout: `/private/tmp/business-ai-telegram-bot.out.log`
- Finance bot stderr: `/private/tmp/business-ai-telegram-bot.err.log`
- Business OS stdout: `~/Library/Logs/BigShotBusinessOS/businessos.log`
- Business OS stderr: `~/Library/Logs/BigShotBusinessOS/businessos-error.log`
- Dashboard stdout: `logs/dashboard_server.out.log`
- Dashboard stderr: `logs/dashboard_server.err.log`

## Graceful Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.bigshot.business-ai.telegram-bot
launchctl kickstart -k gui/$(id -u)/com.bigshot.businessos
launchctl kickstart -k gui/$(id -u)/com.bigshot.business-dashboard
```

Do not use `pkill -9`. launchd owns recovery and process lifecycle.

For a graceful recovery test, send `SIGTERM` through launchd, confirm the bot
logs `stopped`, and verify launchd starts one replacement process.

## Backup

```bash
docker exec postgres pg_dump -U admin -d automationdb -Fc > automationdb.dump
docker exec -i postgres pg_restore -l < automationdb.dump
```

Verify that both the dump and restore-list output are non-empty before modifying
payment logic or database structures.

## Restore Procedure

Never restore over the live database first. Restore into an isolated database:

```bash
docker exec postgres createdb -U admin automationdb_restore_test
docker exec -i postgres pg_restore \
  -U admin \
  -d automationdb_restore_test \
  --no-owner \
  --no-privileges \
  < automationdb.dump
docker exec postgres psql \
  -U admin \
  -d automationdb_restore_test \
  -Atc "select count(*) from information_schema.tables where table_schema='pipkgfu2wr9qxyy';"
```

Validate table counts, payment drift, report totals, and application queries
against the isolated database. Production replacement requires a scheduled
outage, a second current backup, and explicit business-owner approval.

## Disaster Recovery

1. Stop payment entry and notify users.
2. Preserve the failed database volume; do not delete it.
3. Verify the latest dump checksum and `pg_restore -l` output.
4. Restore into a new database and run integrity checks.
5. Point a temporary application process at the restored database.
6. Validate payment search, KPI totals, inventory stock, and Telegram reports.
7. Promote only after business-owner approval.
8. Retain the old volume and incident evidence until reconciliation is complete.

Recovery objective is constrained by backup frequency. Daily 21:00 backups imply
up to 24 hours of data exposure unless additional intra-day backups are added.

## Workflow Verification

- Payment: search exact voucher, post partial payment, verify history and
  materialized summary, then post final payment.
- Inventory: enter production, transfer, and sale as separate movement rows;
  stock is derived from `To_Store` minus `From_Store`.
- Telegram: verify authorized chat/topic routing, one polling lock holder,
  report output, and error logs.
- BI: verify deterministic formula selection, canonical KPI totals, and output
  parity across text, PDF, Excel, executive, and Telegram paths.
- Dashboard: verify global filters refresh all Executive widgets, API responses
  identify canonical sources, exports are non-empty, and browser source contains
  no SQL or database driver.

## Regression Test

```bash
python3 -m unittest discover -s tests
python3 -m py_compile \
  telegram_bot.py \
  business_agent.py \
  business_os_app.py \
  ops/business_os_server.py \
  tools/formula_engine.py \
  tools/ollama_client.py
```

## Payment Integrity Checks

For each transaction row:

```text
Outstanding_Balance = max(Total_Amount - Total_Received, 0)
```

Status:

```text
Paid        when Outstanding_Balance = 0 and Total_Received > 0
Partial     when Total_Received > 0 and Outstanding_Balance > 0
Outstanding when Total_Received = 0
```

## Known Legacy Data

- Some migrated `Payment_Receive` rows have no `Invoice_Date`.
- Some migration snapshots contain negative historical outstanding values.
- Do not automatically rewrite those rows without an approved reconciliation map.
