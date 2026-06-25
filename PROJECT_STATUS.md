# Project Status

- Telegram group: BigShot Family
- Telegram chat_id: -1003850232296
- Finance topic thread_id: 5
- bigshot_lady_bot: working in Finance topic
- PostgreSQL + NocoDB: connected
- Ollama qwen3:14b: local AI runtime

## Bot Entry Points

- Finance/business bot: `telegram_bot.py`
- Legacy KPI bot: `telegram_kpi_bot.py` guarded but not the preferred finance entry point

## Startup Scripts

- `start_bot.sh` exports `TELEGRAM_ALLOWED_CHAT_ID=-1003850232296` and `TELEGRAM_ALLOWED_THREAD_ID=5`

## Verification

- `python3 -m unittest discover -s tests`
- `PYTHONPYCACHEPREFIX=/private/tmp/business-ai-pycache python3 -m py_compile config.example.py telegram_bot.py telegram_kpi_bot.py business_agent.py tools/ollama_client.py tools/formula_engine.py tools/kpi_engine.py tools/ai_kpi_engine.py`
