#!/bin/bash
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$HOME/ai-automation"

open -ga Docker

# Give Docker Desktop time to start after macOS login.
for i in {1..120}; do
  if docker info >/dev/null 2>&1; then
    docker compose up -d
    exit 0
  fi
  sleep 5
done

echo "Docker was not ready after 10 minutes." >&2
exit 1
