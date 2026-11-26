# todolist
A todo list that brings features usually found in premium apps: repeating tasks, priorities, tags, projects,
a pomodoro timer, tracked values, progress charts, and points, levels and streaks.

Documentation: [user guide](docs/user-guide.md) · [development](docs/development.md) · [deployment](docs/deployment.md) 

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DJANGO_DEBUG=true python manage.py migrate
DJANGO_DEBUG=true python manage.py runserver     # http://localhost:8000/todolist/
```

Or with Docker (app + PostgreSQL): `docker compose up --build`, then open http://localhost:8000/todolist/.

### Moving existing data from SQLite to PostgreSQL

```bash
DJANGO_DEBUG=true python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.permission -e sessions > data.json          # from SQLite
DJANGO_DB_HOST=... DJANGO_DB_PASSWORD=... DJANGO_DEBUG=true python manage.py migrate
DJANGO_DB_HOST=... DJANGO_DB_PASSWORD=... DJANGO_DEBUG=true python manage.py loaddata data.json
```

## Tests

```bash
DJANGO_DEBUG=true python manage.py test todolist
```

## Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` or `DJANGO_SECRET_KEY_FILE` | Secret key. Required unless `DJANGO_DEBUG=true` |
| `DJANGO_DEBUG` | `true` for development only |
| `DJANGO_PUBLIC_ORIGIN` | Public address, e.g. `https://example.com`: allowed host, CSRF origin, secure cookies |
| `DJANGO_DB_HOST` | Use PostgreSQL on this host (otherwise SQLite). Also `DJANGO_DB_PORT`, `DJANGO_DB_NAME`, `DJANGO_DB_USER` (default `todolist`), `DJANGO_DB_PASSWORD` or `DJANGO_DB_PASSWORD_FILE` |
| `DJANGO_DB_PATH` | SQLite file location when not using PostgreSQL (the Docker image uses `/data/db.sqlite3`) |

The app is served under `/todolist/`, including static files (WhiteNoise), so it can sit behind a
reverse proxy next to other apps.
