"""Web Push (VAPID) for reminders: keys, sending, and the reminder rules the notifier runs every minute."""
import base64
import datetime
import json
import logging
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import Item, NotificationSettings, PushSubscription, SentNotification

log = logging.getLogger(__name__)
CATCH_UP = datetime.timedelta(minutes=30)   # after downtime, don't send reminders older than this
SUMMARY_WINDOW = datetime.timedelta(hours=2)


# ---------- keys ----------

@lru_cache(maxsize=1)
def _private_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    path = settings.VAPID_PRIVATE_KEY_FILE
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return load_pem_private_key(f.read(), password=None)
    except OSError:
        log.warning("VAPID key file %s can't be read; notifications are off", path)
        return None


def enabled():
    return _private_key() is not None


def public_key():
    """The applicationServerKey browsers need: the uncompressed public point, base64url without padding."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    key = _private_key()
    if key is None:
        return ""
    raw = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ---------- sending ----------

def send(user, title, body="", url=None, tag=None):
    """Send to every device the user turned notifications on for. Returns how many accepted it."""
    if not enabled():
        return 0
    from pywebpush import WebPushException, webpush
    payload = json.dumps({"title": title, "body": body, "url": url or reverse("todolist:index"), "tag": tag})
    claims_sub = settings.VAPID_SUBJECT
    ok = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY_FILE, vapid_claims={"sub": claims_sub}, ttl=3600, timeout=10)
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):      # the device unsubscribed or the app was removed
                sub.delete()
            else:
                PushSubscription.objects.filter(pk=sub.pk).update(failures=sub.failures + 1)
                log.warning("push to %s failed: %s", sub.endpoint[:40], status or e)
            continue
        except Exception as e:  # network trouble: try again next time
            log.warning("push to %s failed: %s", sub.endpoint[:40], e)
            continue
        PushSubscription.objects.filter(pk=sub.pk).update(last_success_at=timezone.now(), failures=0)
        ok += 1
    return ok


def _once(user, kind, key):
    """True the first time (user, kind, key) is seen; False afterwards."""
    try:
        with transaction.atomic():   # a savepoint, so a duplicate doesn't break the surrounding transaction
            SentNotification.objects.create(user=user, kind=kind, key=key[:100])
        return True
    except IntegrityError:
        return False


def user_tz(prefs):
    try:
        return ZoneInfo(prefs.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


# ---------- rules ----------

def due_reminders(now=None):
    """A reminder `lead_minutes` before each one-off task is due (sent once per due time)."""
    now = now or timezone.now()
    sent = 0
    for prefs in NotificationSettings.objects.filter(due_reminders=True, user__push_subscriptions__isnull=False).distinct().select_related("user"):
        lead = datetime.timedelta(minutes=prefs.lead_minutes)
        tz = user_tz(prefs)
        items = (Item.objects.filter(user=prefs.user, status=False, recurring_task=False,
                                     due_date__gt=now + lead - CATCH_UP, due_date__lte=now + lead)
                 .select_related("project"))
        for item in items:
            if not _once(prefs.user, "due", f"{item.id}:{item.due_date.isoformat()}"):
                continue
            at = item.due_date.astimezone(tz).strftime("%H:%M")
            when = "now" if item.due_date <= now else f"at {at}"
            body = f"Due {when}" + (f" · {item.project.name}" if item.project_id else "")
            sent += send(prefs.user, item.todo_item, body, url=reverse("todolist:index"), tag=f"due-{item.id}")
    return sent


def daily_summaries(now=None):
    """Once a day, at the user's chosen local time: what's due today and what's overdue."""
    now = now or timezone.now()
    sent = 0
    for prefs in NotificationSettings.objects.filter(daily_summary=True, user__push_subscriptions__isnull=False).distinct().select_related("user"):
        tz = user_tz(prefs)
        local = now.astimezone(tz)
        start = datetime.datetime.combine(local.date(), prefs.summary_time, tzinfo=tz)
        if not (start <= local < start + SUMMARY_WINDOW):
            continue
        if not _once(prefs.user, "summary", local.date().isoformat()):
            continue
        day_start = datetime.datetime.combine(local.date(), datetime.time.min, tzinfo=tz)
        day_end = datetime.datetime.combine(local.date(), datetime.time.max, tzinfo=tz)
        open_items = Item.objects.filter(user=prefs.user, status=False)
        overdue = open_items.filter(recurring_task=False, due_date__lt=day_start)
        today = open_items.filter(Q(recurring_task=True) | Q(due_date__gte=day_start, due_date__lte=day_end))
        n_today, n_over = today.count(), overdue.count()
        if not n_today and not n_over:
            continue      # nothing to say; stay quiet
        parts = []
        if n_today:
            parts.append(f"{n_today} task{'s' if n_today != 1 else ''} today")
        if n_over:
            parts.append(f"{n_over} overdue")
        names = list(overdue.order_by("due_date").values_list("todo_item", flat=True)[:2]) + \
            list(today.order_by("-itemPriority", "due_date").values_list("todo_item", flat=True)[:3])
        body = ", ".join(parts) + (": " + ", ".join(names[:3]) if names else "")
        if len(names) > 3:
            body += "…"
        sent += send(prefs.user, "Good morning" if local.hour < 12 else "Your day", body,
                     url=reverse("todolist:index"), tag="summary")
    return sent


def run_once(now=None):
    if not enabled():
        return 0
    return due_reminders(now) + daily_summaries(now)
