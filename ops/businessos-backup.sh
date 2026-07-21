#!/bin/bash
set -euo pipefail

PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"
BACKUP_DIR="/Users/bigshot/BusinessOS_Backups"
LOG_DIR="/Users/bigshot/Library/Logs/BigShotBusinessOS"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
FINAL="$BACKUP_DIR/automationdb_$STAMP.dump"
TEMP="$FINAL.partial"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"
trap 'rm -f "$TEMP"' EXIT
docker exec postgres pg_dump -U admin -d automationdb -Fc > "$TEMP"
test -s "$TEMP"
mv "$TEMP" "$FINAL"
trap - EXIT
find "$BACKUP_DIR" -type f -name 'automationdb_*.dump' -mtime +29 -delete
echo "$(date -Iseconds) backup completed: $FINAL"
