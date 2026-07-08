#!/usr/bin/env bash
set -euo pipefail

set -a
source deploy/dashboard.env
set +a

BASE_URL="${DASHBOARD_VERIFY_URL:-http://${DASHBOARD_PUBLISHED_HOST:-127.0.0.1}:${DASHBOARD_PUBLISHED_PORT:-5062}}"
USERNAME="${MASTER_USERNAME:-admin}"
PASSWORD="${MASTER_PASSWORD:-change-this-before-production}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

container_id="$(docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env ps -q business-dashboard)"
if [[ -z "$container_id" ]]; then
  echo "FAIL: business-dashboard container is not running"
  exit 1
fi

running="$(docker inspect -f '{{.State.Running}}' "$container_id")"
if [[ "$running" != "true" ]]; then
  echo "FAIL: business-dashboard container exists but is not running"
  exit 1
fi

health_code="$(curl -sS -o /tmp/dashboard-health.out -w '%{http_code}' "$BASE_URL/health")"
if [[ "$health_code" != "200" ]]; then
  echo "FAIL: health endpoint returned $health_code"
  exit 1
fi

ready_code="$(curl -sS -o /tmp/dashboard-ready.out -w '%{http_code}' "$BASE_URL/ready")"
if [[ "$ready_code" != "200" ]] || ! grep -q '"status":"ready"' /tmp/dashboard-ready.out; then
  echo "FAIL: readiness endpoint returned $ready_code"
  cat /tmp/dashboard-ready.out
  exit 1
fi

route_code="$(curl -sS -o /tmp/dashboard-route.out -w '%{http_code}' "$BASE_URL/payments")"
if [[ "$route_code" != "302" ]]; then
  echo "FAIL: unauthenticated dashboard route returned $route_code, expected 302"
  exit 1
fi

api_code="$(curl -sS -o /tmp/dashboard-api.out -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"filters":{"period":{"type":"year","year":2026}}}' \
  "$BASE_URL/api/dashboard/executive")"
if [[ "$api_code" != "401" ]]; then
  echo "FAIL: unauthenticated dashboard API returned $api_code, expected 401"
  exit 1
fi

login_code="$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -o /tmp/dashboard-login.out -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  "$BASE_URL/api/auth/login")"
if [[ "$login_code" != "200" ]]; then
  echo "FAIL: login endpoint returned $login_code"
  exit 1
fi

session_code="$(curl -sS -b "$COOKIE_JAR" -o /tmp/dashboard-session.out -w '%{http_code}' "$BASE_URL/api/auth/session")"
if [[ "$session_code" != "200" ]] || ! grep -q '"authenticated":true' /tmp/dashboard-session.out; then
  echo "FAIL: authenticated session check failed"
  exit 1
fi

echo "OK: dashboard container, health, route protection, API protection, and login verified at $BASE_URL"
