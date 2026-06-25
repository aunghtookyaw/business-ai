# BigShot AI Business OS — Production Runbook

## Health Checks

```bash
curl http://127.0.0.1:5059/health
curl http://127.0.0.1:8080/api/v1/health
curl http://127.0.0.1:11434/api/tags
docker compose ps
```

## Logs

- Finance bot stdout: `/private/tmp/business-ai-telegram-bot.out.log`
- Finance bot stderr: `/private/tmp/business-ai-telegram-bot.err.log`
- Payment stdout: `logs/receive_payment_server.out.log`
- Payment stderr: `logs/receive_payment_server.err.log`

## Graceful Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.bigshot.business-ai.telegram-bot
launchctl kickstart -k gui/$(id -u)/com.bigshot.receive-payment
```

Do not use `pkill -9`. launchd owns recovery and process lifecycle.

## Backup

```bash
docker exec postgres pg_dump -U admin -d automationdb -Fc > automationdb.dump
docker exec -i postgres pg_restore -l < automationdb.dump
```

Verify that both the dump and restore-list output are non-empty before modifying
payment logic or database structures.

## Regression Test

```bash
python3 -m unittest discover -s tests
python3 -m py_compile \
  telegram_bot.py \
  business_agent.py \
  scripts/receive_payment_server.py \
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
