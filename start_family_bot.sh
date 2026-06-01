#!/bin/bash
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PYTHON_BIN="/usr/bin/python3"

export FAMILY_ALLOWED_CHAT_ID="-1003850232296"
export FAMILY_ALLOWED_THREAD_ID="4"
export FAMILY_IGNORED_THREAD_IDS="5"

pkill -f family_ai_bot.py || true

cd ~/ai-automation/business-ai

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') Starting family_ai_bot.py with $PYTHON_BIN"

exec "$PYTHON_BIN" family_ai_bot.py
