"""Points, levels, streaks and badges (bha123/todolist#36).

Points: finishing a task earns 5 x its priority (5-20); each completed pomodoro earns 2.
Un-ticking a task removes the points it earned, so toggling can't farm points.
Levels: every 100 points. Streak: consecutive days, up to today, with at least one activity
(yesterday still counts so the streak isn't lost before you've done anything today).
"""
import datetime

from django.db.models import Count, Sum
from django.utils import timezone

from .models import Activity

POINTS_PER_PRIORITY = 5
POINTS_PER_POMODORO = 2
POINTS_PER_LEVEL = 100

BADGES = [
    # (id, name, description, test(stats) -> bool)
    ("first-task", "First step", "Finish your first task", lambda s: s["tasks_done"] >= 1),
    ("ten-tasks", "Getting things done", "Finish 10 tasks", lambda s: s["tasks_done"] >= 10),
    ("hundred-tasks", "Centurion", "Finish 100 tasks", lambda s: s["tasks_done"] >= 100),
    ("first-pomodoro", "Focused", "Complete a pomodoro", lambda s: s["pomodoros"] >= 1),
    ("fifty-pomodoros", "Deep worker", "Complete 50 pomodoros", lambda s: s["pomodoros"] >= 50),
    ("streak-3", "On a roll", "A 3-day streak", lambda s: s["best_streak"] >= 3),
    ("streak-7", "Week warrior", "A 7-day streak", lambda s: s["best_streak"] >= 7),
    ("streak-30", "Unstoppable", "A 30-day streak", lambda s: s["best_streak"] >= 30),
    ("level-5", "Level 5", "Reach level 5", lambda s: s["level"] >= 5),
]


def record_task_done(item, when=None):
    when = when or timezone.now()
    Activity.objects.create(user=item.user, kind=Activity.TASK_DONE, item_id=item.id, priority=item.itemPriority,
                            points=POINTS_PER_PRIORITY * int(item.itemPriority or 1), created_at=when)
    type(item).objects.filter(pk=item.pk).update(completed_at=when)


def undo_task_done(item):
    latest = Activity.objects.filter(user=item.user, kind=Activity.TASK_DONE, item_id=item.id).first()
    if latest:
        latest.delete()
    type(item).objects.filter(pk=item.pk).update(completed_at=None)


def record_pomodoro(item, when=None):
    Activity.objects.create(user=item.user, kind=Activity.POMODORO, item_id=item.id, priority=item.itemPriority,
                            points=POINTS_PER_POMODORO, created_at=when or timezone.now())


def status_changed(item, was_done, is_done):
    """Call after a task's done flag changes."""
    if is_done and not was_done:
        record_task_done(item)
    elif was_done and not is_done:
        undo_task_done(item)


def _streaks(days, today):
    """(current streak, best streak) from a set of active dates."""
    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == datetime.timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    current = 0
    start = today if today in days else today - datetime.timedelta(days=1)
    d = start
    while d in days:
        current += 1
        d -= datetime.timedelta(days=1)
    return current, best


def stats(user, today=None):
    today = today or timezone.localdate()
    acts = Activity.objects.filter(user=user)
    totals = dict(acts.values_list("kind").annotate(n=Count("id")).values_list("kind", "n"))
    points = acts.aggregate(p=Sum("points"))["p"] or 0
    days = {timezone.localtime(t).date() for t in acts.values_list("created_at", flat=True)}
    current, best = _streaks(days, today)
    level = points // POINTS_PER_LEVEL + 1
    s = {
        "points": points, "level": level,
        "level_progress": points % POINTS_PER_LEVEL, "points_per_level": POINTS_PER_LEVEL,
        "streak": current, "best_streak": best,
        "tasks_done": totals.get(Activity.TASK_DONE, 0), "pomodoros": totals.get(Activity.POMODORO, 0),
        "points_today": acts.filter(created_at__date=today).aggregate(p=Sum("points"))["p"] or 0,
    }
    s["badges"] = [{"id": b, "name": n, "description": d, "earned": test(s)} for b, n, d, test in BADGES]
    return s


def daily_series(user, days=30, today=None):
    """Per-day counts for the last `days` days: labels, tasks finished, pomodoros, points."""
    today = today or timezone.localdate()
    start = today - datetime.timedelta(days=days - 1)
    labels = [start + datetime.timedelta(days=i) for i in range(days)]
    tasks = dict.fromkeys(labels, 0)
    pomodoros = dict.fromkeys(labels, 0)
    points = dict.fromkeys(labels, 0)
    since = timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
    for kind, created, pts in Activity.objects.filter(user=user, created_at__gte=since).values_list("kind", "created_at", "points"):
        d = timezone.localtime(created).date()
        if d not in points:
            continue
        points[d] += pts
        if kind == Activity.TASK_DONE:
            tasks[d] += 1
        else:
            pomodoros[d] += 1
    return {
        "labels": [d.strftime("%d %b") for d in labels],
        "tasks": [tasks[d] for d in labels], "pomodoros": [pomodoros[d] for d in labels], "points": [points[d] for d in labels],
    }
