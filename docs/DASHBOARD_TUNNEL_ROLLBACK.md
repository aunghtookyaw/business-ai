# Dashboard Reverse SSH Tunnel Rollback

The production architecture uses the VPS Nginx dashboard virtual host at
`127.0.0.1:6062`, forwarded by `com.bigshot.dashboard-tunnel` to the Mac mini
dashboard server at `127.0.0.1:5062`.

## Roll back the LaunchAgent installation

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.bigshot.dashboard-tunnel.plist
rm ~/Library/LaunchAgents/com.bigshot.dashboard-tunnel.plist
```

If a pre-change LaunchAgent backup exists, restore it from the backup directory
recorded during deployment and bootstrap it again:

```bash
cp <backup-directory>/com.bigshot.dashboard-tunnel.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bigshot.dashboard-tunnel.plist
```

## Roll back the internal API token

Restore both token consumers from the same pre-change backup. Never restore one
side alone.

```bash
cp <backup-directory>/dashboard.env deploy/dashboard.env
cp <backup-directory>/com.bigshot.business-dashboard.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.bigshot.business-dashboard.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bigshot.business-dashboard.plist
```

If the prior token is unavailable, generate a fresh token and install that same
value in `deploy/dashboard.env`, the dashboard server LaunchAgent, and every
internal API client before restarting them.

## Roll back the VPS backend target

Restore the timestamped Nginx backup made during deployment, validate it, and
reload Nginx:

```bash
ssh bigshot-vps
cp <backup-directory>/dashboard /etc/nginx/sites-available/dashboard
nginx -t
systemctl reload nginx
```

Only use the former `127.0.0.1:5062` target if a service on the VPS is again
listening there. Otherwise retain `127.0.0.1:6062` so the dashboard continues to
use the approved reverse SSH tunnel.

## Verify after rollback

```bash
curl -fsS http://127.0.0.1:5062/health
ssh bigshot-vps 'curl -fsS http://127.0.0.1:6062/health'
```

Do not change Formula Engine, PostgreSQL, Telegram Bot, Outline VPN, WordPress,
Business Agent, or NocoDB during rollback.
