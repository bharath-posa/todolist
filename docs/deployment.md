# Deployment

## Docker image
The `Dockerfile` builds a Python 3.12 image that serves the app with gunicorn on port 8000. On start it runs
migrations. Static files are collected at build time and served by WhiteNoise.

```bash
docker build -t todolist .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=... -e DJANGO_PUBLIC_ORIGIN=https://example.com todolist
```

## Configuration
| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` or `DJANGO_SECRET_KEY_FILE` | Secret key. Required unless `DJANGO_DEBUG=true` |
| `DJANGO_DEBUG` | `true` for development only |
| `DJANGO_PUBLIC_ORIGIN` | Public address, e.g. `https://example.com`. Adds the host, trusts it for CSRF and makes cookies secure |
| `DJANGO_EXTRA_CSRF_ORIGINS` | Extra comma-separated origins to trust (e.g. `http://localhost:8000`) |
| `DJANGO_DB_HOST` | Use PostgreSQL on this host. With `DJANGO_DB_PORT`, `DJANGO_DB_NAME`, `DJANGO_DB_USER` (default `todolist`) and `DJANGO_DB_PASSWORD` or `DJANGO_DB_PASSWORD_FILE` |
| `DJANGO_DB_PATH` | SQLite file when not using PostgreSQL (image default `/data/db.sqlite3`) |

## Behind a reverse proxy
The app serves everything under `/todolist/` (pages and `/todolist/static/`), and its cookies are scoped to
that path, so it can share a domain with other apps. Forward the path unchanged and set
`X-Forwarded-Proto` and `Host`, e.g. for nginx:

```nginx
location ^~ /todolist/ {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_pass http://todolist:8000;
}
```
The pages load Bootstrap, jQuery and Chart.js from `cdn.jsdelivr.net` and `ajax.googleapis.com` and use
inline scripts, so a Content-Security-Policy must allow those.

## Moving data from SQLite to PostgreSQL
```bash
DJANGO_DEBUG=true python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.permission -e sessions > data.json          # against SQLite
# then, against PostgreSQL:
DJANGO_DB_HOST=... DJANGO_DB_PASSWORD=... DJANGO_DEBUG=true python manage.py migrate
DJANGO_DB_HOST=... DJANGO_DB_PASSWORD=... DJANGO_DEBUG=true python manage.py loaddata data.json
```

## Backups
With PostgreSQL in Docker: `docker compose exec db pg_dump -U todolist todolist > backup.sql`.
(`backupDb2Git.py` is the original SQLite-to-GitHub backup script; it needs a token and isn't used by the
Docker setup.)

## Notifications (Web Push)
Reminders need a VAPID key and a second process that checks once a minute.

1. Make a key (P-256, PEM) and keep it secret; changing it later means every device must turn
   notifications on again:
   ```bash
   openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt -out vapid_private.pem
   ```
2. Give it to the web app **and** the notifier: `DJANGO_VAPID_PRIVATE_KEY_FILE=/run/secrets/vapid_private.pem`.
   `DJANGO_VAPID_SUBJECT` (optional) is the contact push services see; it defaults to `DJANGO_PUBLIC_ORIGIN`
   and must start with `https://` or `mailto:`.
3. Run the notifier with the same image and settings: `python manage.py run_notifier` (or
   `run_notifier --once` from cron every minute). The long-running notifier also checks for finished pomodoro
   timers every 5 seconds (`--timer-interval`); with cron they can arrive up to a minute late. It needs outbound HTTPS to the push services
   (`web.push.apple.com`, `fcm.googleapis.com`, `updates.push.services.mozilla.com`).

The app serves `/todolist/sw.js` (service worker, with `Service-Worker-Allowed: /todolist/`) and
`/todolist/manifest.webmanifest`. Without a key the app works as before and the Notifications page says
notifications aren't set up.

Behind ngrok's free plan, the first visit from a new browser (and the first launch of the Home Screen app,
which keeps its own cookies) shows ngrok's warning page once; after **Visit Site** everything works.
