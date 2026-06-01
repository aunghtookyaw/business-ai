# Project Status

- Telegram group: BigShot Family
- Telegram chat_id: -1003850232296
- Finance topic thread_id: 5
- Family AI Assistant topic thread_id: 4
- bigshot_lady_bot: working in Finance topic
- BigShot_Guy_bot: allowed in the Family AI Assistant topic and connects through OpenClaw
- PostgreSQL + NocoDB: connected

## Bot Entry Points

- Finance/business bot: `telegram_bot.py`
- Family assistant bot: `family_ai_bot.py`, using `tools.openclaw_client`
- Legacy KPI bot: `telegram_kpi_bot.py` guarded but not the preferred finance entry point

## Startup Scripts

- `start_bot.sh` exports `TELEGRAM_ALLOWED_CHAT_ID=-1003850232296` and `TELEGRAM_ALLOWED_THREAD_ID=5`
- `start_family_bot.sh` exports `FAMILY_ALLOWED_CHAT_ID=-1003850232296`, `FAMILY_ALLOWED_THREAD_ID=4`, and `FAMILY_IGNORED_THREAD_IDS=5`

## Verification

- `python3 -m unittest discover -s tests`
- `PYTHONPYCACHEPREFIX=/private/tmp/business-ai-pycache python3 -m py_compile config.example.py family_ai_bot.py telegram_bot.py telegram_kpi_bot.py business_agent.py tools/openclaw_client.py tools/formula_engine.py tools/kpi_engine.py tools/ai_kpi_engine.py`
