# business-ai

Local business automation and Telegram AI assistant project.

## Current Telegram Topics

- BigShot Family chat_id: `-1003850232296`
- Finance topic thread_id: `5`
- Family AI Assistant thread_id: `4`

## Bots

- `telegram_bot.py`: Bigshot Lady business finance bot. It answers only in the Finance topic when started with `start_bot.sh`.
- `family_ai_bot.py`: BigShot_Guy_Bot family assistant. It answers only in the Family AI Assistant topic and sends prompts through `tools.openclaw_client`.
- `telegram_kpi_bot.py`: older KPI bot entry point. It is topic-guarded, but `telegram_bot.py` is the preferred finance bot.

## Required Environment

Create a local `config.py` from `config.example.py`, then set real tokens and service values.

Important variables:

- `TELEGRAM_BOT_TOKEN`
- `FAMILY_TELEGRAM_BOT_TOKEN` or `BIGSHOT_GUY_BOT_TOKEN`
- `FAMILY_ALLOWED_CHAT_ID`
- `FAMILY_ALLOWED_THREAD_ID` defaults to Family AI Assistant topic `4`
- `FAMILY_IGNORED_THREAD_IDS` optional comma-separated topic IDs to ignore, defaults to Finance topic `5`
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
./start_family_bot.sh
```

To check the BigShot_Guy_bot token and group membership:

```bash
python3 scripts/check_family_bot.py
```

## Test

```bash
python3 -m unittest discover -s tests
PYTHONPYCACHEPREFIX=/private/tmp/business-ai-pycache python3 -m py_compile config.example.py family_ai_bot.py telegram_bot.py telegram_kpi_bot.py business_agent.py tools/openclaw_client.py tools/formula_engine.py tools/kpi_engine.py tools/ai_kpi_engine.py
```
