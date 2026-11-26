# todolist
This is a todolist applications which tries to incorporate features that are premium in commerical applications 

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DJANGO_DEBUG=true python manage.py migrate
DJANGO_DEBUG=true python manage.py runserver     # http://localhost:8000/todolist/
```

Or with Docker: `docker compose up --build`, then open http://localhost:8000/todolist/.

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
| `DJANGO_DB_PATH` | SQLite file location (the Docker image uses `/data/db.sqlite3`) |

The app is served under `/todolist/`, including static files (WhiteNoise), so it can sit behind a
reverse proxy next to other apps.
