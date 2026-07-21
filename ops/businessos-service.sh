#!/bin/bash
set -u

PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT_ROOT="/Users/bigshot/ai-automation/business-ai"
COMPOSE_ROOT="/Users/bigshot/ai-automation"
LOG_DIR="/Users/bigshot/Library/Logs/BigShotBusinessOS"

mkdir -p "$LOG_DIR"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$PROJECT_ROOT" || exit 1

if ! docker info >/dev/null 2>&1; then
  open -ga Docker >/dev/null 2>&1 || true
fi

docker_ready=0
for _ in $(seq 1 120); do
  if docker info >/dev/null 2>&1; then
    docker_ready=1
    break
  fi
  sleep 5
done

if [ "$docker_ready" -ne 1 ]; then
  echo "$(date -Iseconds) Docker was not ready after 10 minutes" >&2
  exit 1
fi

if ! docker compose --project-directory "$COMPOSE_ROOT" ps --status running postgres nocodb 2>/dev/null | grep -q postgres; then
  docker compose --project-directory "$COMPOSE_ROOT" up -d postgres nocodb
fi

postgres_ready=0
for _ in $(seq 1 120); do
  if docker exec postgres pg_isready -U admin -d automationdb >/dev/null 2>&1; then
    postgres_ready=1
    break
  fi
  sleep 2
done

if [ "$postgres_ready" -ne 1 ]; then
  echo "$(date -Iseconds) PostgreSQL was not ready after 4 minutes" >&2
  exit 1
fi

for _ in $(seq 1 120); do
  if curl --fail --silent --max-time 2 http://127.0.0.1:8080/ >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

exec /usr/bin/python3 "$PROJECT_ROOT/ops/business_os_server.py"
