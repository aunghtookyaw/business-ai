# business-ai

Local business automation and Telegram AI assistant project.

## Veggies Production

Daily vegetable production architecture, Excel import workflow, database migration,
NocoDB setup, duplicate rules, and recovery instructions are documented in
[`docs/FARM_PRODUCTION_SYSTEM.md`](docs/FARM_PRODUCTION_SYSTEM.md).

## Current Telegram Topic

- BigShot Family chat_id: `-1003850232296`
- Finance topic thread_id: `5`

## Bots

- `telegram_bot.py`: Bigshot Lady business finance bot. It answers only in the Finance topic when started with `start_bot.sh`.
- `telegram_kpi_bot.py`: older KPI bot entry point. It is topic-guarded, but `telegram_bot.py` is the preferred finance bot.

## Required Environment

Create a local `config.py` from `config.example.py`, then set real tokens and service values.

Important variables:

- `TELEGRAM_BOT_TOKEN`
- `NOCODB_URL`
- `NOCODB_API_TOKEN`
- `POSTGRES_HOST`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`

## Run

```bash
./start_bot.sh
```

Executive Dashboard:

```bash
python3 scripts/dashboard_server.py
```

Open `http://127.0.0.1:5062`.

To verify the local Ollama model:

```bash
python3 scripts/check_local_ai.py
```

## Test

```bash
python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX=/private/tmp/business-ai-pycache python3 -m py_compile config.example.py telegram_bot.py telegram_kpi_bot.py business_agent.py tools/ollama_client.py tools/formula_engine.py tools/kpi_engine.py tools/ai_kpi_engine.py
```
