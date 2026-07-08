# BigShot Business Dashboard Production Deployment

Target host: DigitalOcean Ubuntu VPS  
Target domain: `dashboard.bigshotagribusiness.com`  
Deployment directory: `/opt/bigshot-dashboard`

This guide deploys only the Business Dashboard container behind Nginx HTTPS.
Do not change WordPress, the Namecheap public website, Formula Engine logic,
PostgreSQL, NocoDB, Telegram Bot, Business Agent, or Ollama during this deploy.

## A. Server Preparation

SSH into the VPS:

```bash
ssh root@YOUR_VPS_IP
```

Update packages:

```bash
apt update
apt upgrade -y
```

Install Docker dependencies:

```bash
apt install -y ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
```

Add Docker apt repository:

```bash
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
apt update
```

Install Docker Engine and Docker Compose plugin:

```bash
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

Verify Docker:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

## B. Create Deployment Directory

```bash
mkdir -p /opt/bigshot-dashboard
chown -R root:root /opt/bigshot-dashboard
chmod 755 /opt/bigshot-dashboard
```

## C. Upload Project Files From Mac

Run this from the Mac:

```bash
cd /Users/bigshot/ai-automation/business-ai
rsync -az --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'deploy/dashboard.env' \
  ./ root@YOUR_VPS_IP:/opt/bigshot-dashboard/
```

Alternative with `scp`:

```bash
cd /Users/bigshot/ai-automation
tar --exclude='business-ai/.git' \
    --exclude='business-ai/deploy/dashboard.env' \
    -czf /tmp/bigshot-dashboard.tar.gz business-ai
scp /tmp/bigshot-dashboard.tar.gz root@YOUR_VPS_IP:/opt/
ssh root@YOUR_VPS_IP 'rm -rf /opt/bigshot-dashboard && mkdir -p /opt/bigshot-dashboard && tar -xzf /opt/bigshot-dashboard.tar.gz -C /opt/bigshot-dashboard --strip-components=1'
```

## D. Create Production Environment File

On the VPS:

```bash
cd /opt/bigshot-dashboard
install -m 0600 /dev/null deploy/dashboard.env
nano deploy/dashboard.env
```

Use this template and replace every placeholder before production use. Do not
commit this file after filling it in:

```bash
MASTER_USERNAME=bigshot_admin
MASTER_PASSWORD=replace-with-production-password
SESSION_SECRET=replace-with-64-plus-character-random-secret
DASHBOARD_PORT=5062
DASHBOARD_COOKIE_SECURE=1
DASHBOARD_PUBLISHED_HOST=127.0.0.1
DASHBOARD_PUBLISHED_PORT=5062

# Use existing production BI database values. Do not create or modify databases.
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5433
POSTGRES_DB=replace-with-existing-db
POSTGRES_USER=replace-with-existing-db-user
POSTGRES_PASSWORD=replace-with-existing-db-password
```

Lock down the file:

```bash
chmod 600 /opt/bigshot-dashboard/deploy/dashboard.env
```

Generate a strong session secret if needed:

```bash
openssl rand -hex 32
```

The compose file maps `SESSION_SECRET` into the Flask session secret. Use the
production password supplied through your private channel for `MASTER_PASSWORD`.
Do not put real passwords or generated session secrets in
`deploy/dashboard.env.example`.

## E. Build And Run Dashboard

```bash
cd /opt/bigshot-dashboard
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env up -d --build
```

## F. Verify Container

```bash
docker ps
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env ps
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env logs --tail=100 business-dashboard
curl -i http://127.0.0.1:5062
curl -i http://127.0.0.1:5062/health
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{"filters":{"period":{"type":"year","year":2026}}}' \
  http://127.0.0.1:5062/api/dashboard/executive
```

Expected results:

- `docker ps` shows `bigshot-business-dashboard` running.
- `/health` returns HTTP `200`.
- `/api/dashboard/executive` returns HTTP `401` before login.
- `/` returns the dashboard HTML containing the login form.
- Login failures return an error message and lock out an IP after 5 failures in
  15 minutes.

Optional deployment script:

```bash
cd /opt/bigshot-dashboard
scripts/verify_dashboard_deploy.sh
```

## G. Configure Nginx Reverse Proxy

Install Nginx and Certbot:

```bash
apt install -y nginx certbot python3-certbot-nginx
systemctl enable --now nginx
```

Confirm DNS for `dashboard.bigshotagribusiness.com` points to the VPS public IP
before requesting a certificate:

```bash
dig +short dashboard.bigshotagribusiness.com
curl -I http://dashboard.bigshotagribusiness.com
```

Create a temporary HTTP-only Nginx site first. This avoids `nginx -t` failing
before Let’s Encrypt certificate files exist.

```bash
cat > /etc/nginx/sites-available/bigshot-dashboard <<'EOF'
server {
    listen 80;
    server_name dashboard.bigshotagribusiness.com;

    location / {
        proxy_pass http://127.0.0.1:5062;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

## H. Enable Nginx Site

```bash
ln -sf /etc/nginx/sites-available/bigshot-dashboard /etc/nginx/sites-enabled/bigshot-dashboard
```

Do not remove or edit any WordPress or public website Nginx config.

## I. Test Nginx Config

```bash
nginx -t
systemctl reload nginx
curl -I http://dashboard.bigshotagribusiness.com
```

## J. Install HTTPS Certificate Using Certbot

```bash
certbot --nginx -d dashboard.bigshotagribusiness.com
```

Choose the redirect option if Certbot asks whether to redirect HTTP to HTTPS.

Verify certificate renewal:

```bash
certbot renew --dry-run
```

## K. Force HTTPS Only

After Certbot creates the certificate, replace the temporary site with the
checked-in production Nginx config:

```bash
cp /opt/bigshot-dashboard/deploy/nginx-dashboard.conf /etc/nginx/sites-available/bigshot-dashboard
nginx -t
systemctl reload nginx
```

The production config redirects HTTP to HTTPS and proxies HTTPS traffic to
`http://127.0.0.1:5062`.

## L. Verify Final Access

From the VPS:

```bash
curl -I https://dashboard.bigshotagribusiness.com
curl -sS https://dashboard.bigshotagribusiness.com | grep -i 'loginForm'
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{"filters":{"period":{"type":"year","year":2026}}}' \
  https://dashboard.bigshotagribusiness.com/api/dashboard/executive
```

From a browser:

```text
https://dashboard.bigshotagribusiness.com
```

Expected browser flow:

- Login page displays first.
- Wrong password shows an error.
- Correct master credentials show the dashboard.
- Logout returns to the login screen.
- Direct dashboard routes redirect to login when logged out.

## Safety

- Keep `/opt/bigshot-dashboard/deploy/dashboard.env` private.
- Never commit `deploy/dashboard.env`.
- Use a strong production password, not the placeholder.
- Use a strong random `SESSION_SECRET`.
- Keep only `deploy/dashboard.env.example` in Git.
- Session cookies are configured as Secure, HttpOnly, and SameSite=Strict.
- Authenticated sessions expire after 10 hours.
- Failed login attempts are rate limited to 5 per IP within 15 minutes.
- Back up deployment files before replacing them:

```bash
mkdir -p /opt/bigshot-dashboard-backups
tar -czf /opt/bigshot-dashboard-backups/dashboard-deploy-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C /opt bigshot-dashboard/deploy
```

## Rollback

View logs:

```bash
cd /opt/bigshot-dashboard
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env logs --tail=200 business-dashboard
```

Stop container:

```bash
cd /opt/bigshot-dashboard
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env down
```

Rebuild the previous uploaded version:

```bash
cd /opt/bigshot-dashboard
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env up -d --build
```

Restart service without rebuilding:

```bash
cd /opt/bigshot-dashboard
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env restart business-dashboard
```

Restore a backed-up deploy directory if needed:

```bash
cd /opt
tar -xzf /opt/bigshot-dashboard-backups/dashboard-deploy-YYYYMMDD-HHMMSS.tar.gz
cd /opt/bigshot-dashboard
docker compose -f deploy/docker-compose.dashboard.yml --env-file deploy/dashboard.env up -d --build
nginx -t
systemctl reload nginx
```

## Deployment Checklist

- [ ] DNS `dashboard.bigshotagribusiness.com` points to the VPS.
- [ ] Docker and Docker Compose plugin are installed.
- [ ] Project files are uploaded to `/opt/bigshot-dashboard`.
- [ ] `/opt/bigshot-dashboard/deploy/dashboard.env` exists with `chmod 600`.
- [ ] `MASTER_USERNAME` is set to `bigshot_admin`.
- [ ] `MASTER_PASSWORD` placeholder is replaced with the private production password.
- [ ] `SESSION_SECRET` placeholder is replaced with a random secret.
- [ ] Dashboard container builds successfully.
- [ ] Container is running and healthy.
- [ ] `curl http://127.0.0.1:5062/health` returns `200`.
- [ ] Unauthenticated API returns `401`.
- [ ] Temporary Nginx HTTP proxy passes `nginx -t`.
- [ ] Certbot certificate is issued.
- [ ] Production Nginx config is enabled after certificate creation.
- [ ] `https://dashboard.bigshotagribusiness.com` shows the login page.
- [ ] Wrong password is rejected.
- [ ] Correct master login shows dashboard.
- [ ] Logout works.
