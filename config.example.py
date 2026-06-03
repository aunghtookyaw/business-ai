import os


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")

TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID")

TELEGRAM_ALLOWED_THREAD_ID = os.getenv("TELEGRAM_ALLOWED_THREAD_ID")

FAMILY_TELEGRAM_BOT_TOKEN = os.getenv("FAMILY_TELEGRAM_BOT_TOKEN", "PUT_YOUR_FAMILY_TELEGRAM_BOT_TOKEN_HERE")

# Optional alias accepted by family_ai_bot.py and scripts/check_family_bot.py.
BIGSHOT_GUY_BOT_TOKEN = os.getenv("BIGSHOT_GUY_BOT_TOKEN", "")

FAMILY_ALLOWED_CHAT_ID = os.getenv("FAMILY_ALLOWED_CHAT_ID", "-1003850232296")

# BigShot_Guy_Bot topic.
FAMILY_ALLOWED_THREAD_ID = os.getenv("FAMILY_ALLOWED_THREAD_ID", "4")

# Comma-separated topic IDs the family bot should ignore, e.g. Finance.
FAMILY_IGNORED_THREAD_IDS = os.getenv("FAMILY_IGNORED_THREAD_IDS", "5")

FAMILY_AI_MODEL = os.getenv("FAMILY_AI_MODEL", "gemma4:e4b")

FAMILY_DEFAULT_WEATHER_LOCATION = os.getenv("FAMILY_DEFAULT_WEATHER_LOCATION", "Yangon")

THAILAND_VEGETABLE_PRICE_URLS = os.getenv(
    "THAILAND_VEGETABLE_PRICE_URLS",
    "https://checkraka.app/price/vegetable-today/makro/,https://checkraka.app/price/vegetable-today/simummuang/",
)

MYANMAR_VEGETABLE_PRICE_URLS = os.getenv(
    "MYANMAR_VEGETABLE_PRICE_URLS",
    "https://www.selinawamucii.com/insights/prices/myanmar/lettuce/,https://www.selinawamucii.com/insights/prices/myanmar/vegetables/",
)

NOCODB_URL = os.getenv("NOCODB_URL", "http://localhost:8080")

NOCODB_API_TOKEN = os.getenv("NOCODB_API_TOKEN", "PUT_YOUR_NOCODB_TOKEN_HERE")

TABLE_ID = os.getenv("TABLE_ID", "moslcqfantzr0mo")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

AI_MODEL = os.getenv("AI_MODEL", "qwen3:latest")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")

POSTGRES_DB = os.getenv("POSTGRES_DB", "automationdb")

POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")

POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "strongpassword")

POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5433")

TRANSACTION_SCHEMA = os.getenv("TRANSACTION_SCHEMA", "pipkgfu2wr9qxyy")

TRANSACTION_TABLE = os.getenv("TRANSACTION_TABLE", "Transection")

LOCAL_UTC_OFFSET_MINUTES = int(os.getenv("LOCAL_UTC_OFFSET_MINUTES", "390"))
