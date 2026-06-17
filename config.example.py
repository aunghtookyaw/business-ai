import os


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")

TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID")

TELEGRAM_ALLOWED_THREAD_ID = os.getenv("TELEGRAM_ALLOWED_THREAD_ID")

FAMILY_TELEGRAM_BOT_TOKEN = os.getenv("FAMILY_TELEGRAM_BOT_TOKEN", "PUT_YOUR_FAMILY_TELEGRAM_BOT_TOKEN_HERE")

FAMILY_ALLOWED_CHAT_ID = os.getenv("FAMILY_ALLOWED_CHAT_ID", "-1003850232296")

# BigShot_Guy_Bot topic.
FAMILY_ALLOWED_THREAD_ID = os.getenv("FAMILY_ALLOWED_THREAD_ID", "4")

# Comma-separated topic IDs the family bot should ignore, e.g. Finance.
FAMILY_IGNORED_THREAD_IDS = os.getenv("FAMILY_IGNORED_THREAD_IDS", "5")

FAMILY_AI_MODEL = os.getenv("FAMILY_AI_MODEL", "qwen3:14b")

FAMILY_DEFAULT_WEATHER_LOCATION = os.getenv("FAMILY_DEFAULT_WEATHER_LOCATION", "BigShot Farm")

THAILAND_VEGETABLE_PRICE_URLS = os.getenv(
    "THAILAND_VEGETABLE_PRICE_URLS",
    "https://checkraka.app/price/vegetable-today/makro/,https://checkraka.app/price/vegetable-today/simummuang/",
)

MYANMAR_VEGETABLE_PRICE_URLS = os.getenv(
    "MYANMAR_VEGETABLE_PRICE_URLS",
    "https://www.selinawamucii.com/insights/prices/myanmar/lettuce/,https://www.selinawamucii.com/insights/prices/myanmar/vegetables/",
)

MYANMAR_RETAIL_VEGETABLE_PRICE_URLS = os.getenv(
    "MYANMAR_RETAIL_VEGETABLE_PRICE_URLS",
    "https://www.makropro.com.mm/en/c/fruit-vegetables/vegetables,https://www.citymall.com.mm/citymall/my/%E1%80%95%E1%80%85%E1%80%B9%E1%80%85%E1%80%8A%E1%80%BA%E1%80%B8%E1%80%A1%E1%80%99%E1%80%BB%E1%80%AD%E1%80%AF%E1%80%B8%E1%80%A1%E1%80%85%E1%80%AC%E1%80%B8%E1%80%99%E1%80%BB%E1%80%AC%E1%80%B8/Brands/City-Farm/c/C0392",
)

NOCODB_URL = os.getenv("NOCODB_URL", "http://localhost:8080")

NOCODB_API_TOKEN = os.getenv("NOCODB_API_TOKEN", "PUT_YOUR_NOCODB_TOKEN_HERE")

TABLE_ID = os.getenv("TABLE_ID", "moslcqfantzr0mo")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

AI_MODEL = os.getenv("AI_MODEL", "qwen3:14b")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")

POSTGRES_DB = os.getenv("POSTGRES_DB", "automationdb")

POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")

POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "strongpassword")

POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5433")

TRANSACTION_SCHEMA = os.getenv("TRANSACTION_SCHEMA", "pipkgfu2wr9qxyy")

TRANSACTION_TABLE = os.getenv("TRANSACTION_TABLE", "Transection")

FARM_TRANSECTION_TABLE = os.getenv("FARM_TRANSECTION_TABLE", "farm_transection")

SOTEPHWAR_TRANSECTION_TABLE = os.getenv("SOTEPHWAR_TRANSECTION_TABLE", "Sotephwar_Transection")

SOTEPHWAR_INVENTORY_TABLE = os.getenv("SOTEPHWAR_INVENTORY_TABLE", "Sotephwar_Inventory")

FINANCIAL_OBLIGATIONS_TABLE = os.getenv("FINANCIAL_OBLIGATIONS_TABLE", "Financial_Obligations")

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "bigshotagribusiness@gmail.com")

GOOGLE_CALENDAR_CREDENTIALS_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "google_calendar_credentials.json")

GOOGLE_CALENDAR_TOKEN_FILE = os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "google_calendar_token.json")

GOOGLE_CALENDAR_TIMEZONE = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "Asia/Yangon")

# 10080=7 days, 4320=3 days, 1440=1 day before the due date.
GOOGLE_CALENDAR_REMINDER_MINUTES = os.getenv("GOOGLE_CALENDAR_REMINDER_MINUTES", "10080,4320,1440")

LOCAL_UTC_OFFSET_MINUTES = int(os.getenv("LOCAL_UTC_OFFSET_MINUTES", "390"))
