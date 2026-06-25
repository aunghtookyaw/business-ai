#!/bin/bash
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PYTHON_BIN="/usr/bin/python3"
export SSL_CERT_FILE="$("$PYTHON_BIN" -c 'import certifi; print(certifi.where())')"

export TELEGRAM_ALLOWED_CHAT_ID="-1003850232296"
export TELEGRAM_ALLOWED_THREAD_ID="5"

cd ~/ai-automation/business-ai

for i in {1..120}; do
  if "$PYTHON_BIN" - <<'PY'
import psycopg2
from config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

conn = psycopg2.connect(
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
)
conn.close()
PY
  then
    exec "$PYTHON_BIN" telegram_bot.py
  fi
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') PostgreSQL not ready; retry $i/120" >&2
  sleep 5
done

echo "PostgreSQL was not ready after 10 minutes." >&2
exit 1
