# Development

## Run it
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DJANGO_DEBUG=true python manage.py migrate
DJANGO_DEBUG=true python manage.py runserver          # http://localhost:8000/todolist/
```
With Docker and PostgreSQL instead: `docker compose up --build`.

## Tests
```bash
DJANGO_DEBUG=true python manage.py test todolist
```
CI (`.github/workflows/tests.yml`) runs the tests on SQLite and PostgreSQL, fails on model changes without a
migration (`makemigrations --check`), checks that production settings refuse to start without a secret key,
and builds the Docker image.

## Layout
| Path | Purpose |
|---|---|
| `mysite/settings.py` | All configuration, read from environment variables (see [deployment](deployment.md)) |
| `todolist/models.py` | `Item` (task), `Project`, `Activity` (points log), `Metric` and `MetricEntry`, repeat periods |
| `todolist/forms.py` | Task, project and metric forms with validation |
| `todolist/views.py` | Task list, add/edit/delete, status toggle, pomodoro count, sign-in and sign-up |
| `todolist/views_extra.py` | Projects, metrics and Insights pages |
| `todolist/game.py` | Points, levels, streaks, badges and the daily series for charts |
| `todolist/context_processors.py` | Level/points/streak for the top bar |
| `todolist/templates/todolist/` | `base.html` layout; `_item.html` one task; `_item_form.html` add/edit |
| `todolist/static/todolist/` | Styles (served by WhiteNoise under `/todolist/static/`) |
| `polls/` | Leftover Django tutorial app; not linked from the UI |

## How things work
- **Ownership.** Every view that loads a task, project, metric or entry filters by the signed-in user and
  returns 404 otherwise. Forms only offer the user's own projects.
- **Repeats.** `Item.recurrence` is the source of truth; `Item.recurring_task` is kept in sync for older
  queries. `Item.reset_if_new_period(today)` compares `period_key(recurrence, last_reset)` with today's and
  resets the task when they differ. The task list runs this for the signed-in user's tasks.
- **Points.** `game.status_changed()` records or removes a `task_done` activity whenever a task's done flag
  changes (checkbox, edit form, pomodoro auto-complete). `game.record_pomodoro()` logs each pomodoro.
  `game.stats()` derives points, level, streaks and badges from the log.
- **Front end.** Server-rendered Django templates with Bootstrap 5.0.2, jQuery 3.4.1 (status toggle,
  filters, tabs) and Chart.js 4.4.1 (Insights and metric charts), all from CDNs.
