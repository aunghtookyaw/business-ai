# BigShot AI Business OS — Production Architecture

Last validated: June 25, 2026

## Architecture Diagram

```text
Telegram Finance Topic
        |
        v
 telegram_bot.py
        |
        +--> business_agent.py --------+
        +--> bi_executor.py            |
        +--> executive_agent.py        +--> formula_engine.py --> PostgreSQL :5433
        +--> chart_pdf.py              |
        +--> ollama_client.py ---------+--> Ollama :11434 / qwen3:14b

Browser
  |
  v
receive_payment_server.py :5059
  |
  +--> Payment_Receive
  +--> farm_transection
  +--> Sotephwar_Transection

NocoDB :8080 --> PostgreSQL :5433
```

## Runtime Service Diagram

```text
macOS launchd
  |
  +--> com.bigshot.business-ai.docker-stack
  |      +--> PostgreSQL container
  |      +--> NocoDB container
  |
  +--> com.bigshot.business-ai.telegram-bot (KeepAlive)
  |      +--> start_bot.sh
  |             +--> database readiness check
  |             +--> telegram_bot.py
  |
  +--> com.bigshot.receive-payment (KeepAlive)
         +--> receive_payment_server.py

Ollama.app
  +--> qwen3:14b
```

## Startup Flow

```text
macOS login
  |
  +--> Docker LaunchAgent
  |      +--> wait for Docker
  |      +--> docker compose up -d
  |
  +--> Finance Bot LaunchAgent
  |      +--> start_bot.sh
  |      +--> retry PostgreSQL connection
  |      +--> acquire single-instance lock
  |      +--> start Telegram polling
  |
  +--> Payment LaunchAgent
         +--> start localhost Flask service on 5059
```

The Finance bot and payment server use launchd `KeepAlive` for automatic recovery.
The Finance bot also uses `/private/tmp/business-ai-finance-bot.lock` to prevent
duplicate polling.

## Module Dependency Diagram

```text
telegram_bot.py
  +--> business_agent.py
  |      +--> formula_engine.py
  |      +--> ollama_client.py
  +--> bi_executor.py
  |      +--> formula_engine.py
  +--> executive_agent.py
  |      +--> executive_tools.py
  |      |      +--> formula_engine.py
  |      +--> ollama_client.py
  +--> chart_pdf.py
  +--> comparison_reports.py
  +--> google_calendar_client.py

receive_payment_server.py
  +--> formula_engine.py
  +--> PostgreSQL

excel_import_server.py
  +--> excel_importer.py
         +--> formula_engine.py
         +--> master_relink_db.py
```

## Database Diagram

```text
customer_master
  +--> _nc_m2m_Sotephwar_Trans_customer_master
  |      +--> Sotephwar_Transection
  +--> _nc_m2m_farm_transectio_customer_master
         +--> farm_transection

category_master
  +--> _nc_m2m_Transection_category_master
         +--> Transection

Payment_Receive
  +--> logical voucher identity:
       Sector + Voucher_Number + Invoice_Date + Customer

Sotephwar_Inventory
  +--> standalone inventory movement ledger

Financial_Obligations
  +--> reminder/calendar data only

fixed_assests
  +--> standalone fixed-asset register
```

NocoDB junction relationships are application-managed. Unique pair indexes prevent
duplicate links. Foreign keys are not currently declared.

## Payment Flow

```text
Search vouchers
  |
  v
Select exact voucher identity
  |  Sector + Voucher Number + Date + Customer
  v
Enter Receive Amount / Method / Reference / Note
  |
  v
save_payment_receive()
  |
  +--> begin database transaction
  +--> acquire voucher advisory lock
  +--> validate one exact voucher
  +--> calculate previous received amount
  +--> reject overpayment
  +--> insert Payment_Receive history
  +--> allocate Total_Received across voucher rows
  +--> calculate Outstanding_Balance
  +--> calculate Payment_Status
  +--> commit
  |
  +--> any exception: rollback
```

`Payment_Receive` is the accounting history. Transaction tables contain materialized
voucher summaries.

## Inventory Flow

```text
Production / Transfer / Sale movement
  |
  v
Sotephwar_Inventory
  |
  +--> movement summary
  +--> stock by product
  +--> stock by store
  +--> Telegram BI / report output
```

Inventory values are derived from movement rows. Sales quantities in
`Sotephwar_Transection` are not used as the inventory ledger.

## Telegram Flow

```text
Telegram update
  |
  +--> chat/thread authorization
  +--> command / callback / text routing
  |
  +--> guided BI intent --> bi_executor
  +--> formula question --> business_agent
  +--> executive question --> executive_agent
  |
  +--> formula_engine SQL
  +--> optional Ollama narrative
  +--> text / PDF / Excel response
```

Unhandled update failures are written through the bot logger. launchd restarts the
process if it exits.

## KPI Flow

```text
Report request
  |
  v
formula_engine canonical KPI path
  |
  +--> Transection expenses
  +--> Transection non-Sote income
  +--> farm_transection Total_Amount
  +--> Sotephwar_Transection Total_Amount
  |
  +--> Total Income
  +--> Total Expense
  +--> Net Profit
  +--> Profit Margin
```

Sote Phwar income duplicated in `Transection` is excluded once at the SQL layer.
BI, executive, PDF, Excel, and Telegram paths consume the same formula result.

Payment reporting uses:

- `Total_Amount`
- `Total_Received`
- `Outstanding_Balance`

## API Map

### Receive Payment — `127.0.0.1:5059`

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Main Receive Payment page |
| GET | `/receive-payment` | Main Receive Payment page |
| GET/POST | `/receive-payment-basic` | Approved Basic workflow |
| GET | `/api/vouchers` | Voucher search/list |
| GET | `/api/voucher` | Exact grouped voucher |
| POST | `/api/payment-receive` | Post payment |
| GET | `/health` | Health check |

### Excel Import — `127.0.0.1:5055`

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/import` | JSON workbook import |
| POST | `/import-vba` | VBA-compatible import |

## Operational Boundaries

- Do not rename existing database tables.
- Do not run `sync_voucher_payment_summaries()` without a current database backup.
- Legacy `Payment_Receive` rows with missing invoice dates require manual reconciliation.
- The payment server is localhost-only.
- PostgreSQL, NocoDB, Telegram, Ollama, and qwen3:14b remain required components.
