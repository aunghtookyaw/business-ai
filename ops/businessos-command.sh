#!/bin/bash
set -u

SERVICE="com.bigshot.businessos"
DOMAIN="gui/$(id -u)"
PLIST="/Users/bigshot/Library/LaunchAgents/$SERVICE.plist"
ACTION="${0##*/}"
ACTION="${ACTION#businessos-}"

case "$ACTION" in
  start)
    if ! launchctl print "$DOMAIN/$SERVICE" >/dev/null 2>&1; then
      launchctl bootstrap "$DOMAIN" "$PLIST" || exit $?
    fi
    launchctl kickstart "$DOMAIN/$SERVICE"
    ;;
  stop)
    launchctl bootout "$DOMAIN/$SERVICE"
    ;;
  restart)
    launchctl kickstart -k "$DOMAIN/$SERVICE"
    ;;
  status)
    launchctl print "$DOMAIN/$SERVICE" 2>/dev/null || true
    echo
    curl --silent --show-error --max-time 5 http://127.0.0.1:5059/status || true
    echo
    ;;
  *)
    echo "Usage: businessos-{start|stop|restart|status}" >&2
    exit 2
    ;;
esac
