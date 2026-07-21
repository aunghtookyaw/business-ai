#!/bin/bash
set -u

PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
LOG_DIR="/Users/bigshot/Library/Logs/BigShotBusinessOS"
RESTART_LOG="$LOG_DIR/health-monitor-restarts.log"
mkdir -p "$LOG_DIR"

if ! curl --fail --silent --max-time 5 http://127.0.0.1:5059/health >/dev/null 2>&1; then
  echo "$(date -Iseconds) localhost:5059 unavailable; restarting com.bigshot.businessos" >> "$RESTART_LOG"
  launchctl kickstart -k "gui/$(id -u)/com.bigshot.businessos" >> "$RESTART_LOG" 2>&1
fi
