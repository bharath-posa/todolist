"""Sync weigh-ins (or any metric) from Apple Health through an iPhone Shortcut.

The Shortcut sends POST /todolist/api/metric-entries/ with
    Authorization: Bearer <personal key>
and a JSON body such as
    {"metric": "Weight", "value": 72.4, "unit": "kg", "recorded_at": "2026-11-26T07:45:00+05:30"}
"""
import hashlib
import json
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from .models import Metric, MetricEntry, PersonalKey

KG_PER_LB = 0.45359237
UNIT_ALIASES = {"kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
                "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb"}
SAME_ENTRY_WINDOW = 120   # seconds: a re-sent Health sample isn't saved twice


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_key(user):
    """Make (or replace) the user's key and return it. Only its hash is kept."""
    key = "tl_" + secrets.token_urlsafe(32)
    PersonalKey.objects.filter(user=user).delete()
    PersonalKey.objects.create(user=user, key_hash=hash_key(key), prefix=key[:8])
    return key


def _user_for(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    pk = PersonalKey.objects.select_related("user").filter(key_hash=hash_key(auth[7:].strip())).first()
    if not pk or not pk.user.is_active:
        return None
    PersonalKey.objects.filter(pk=pk.pk).update(last_used_at=timezone.now())
    return pk.user


def _number(raw):
    """72.4, "72.4", "72,4" and "72.4 kg" all give 72.4."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(raw or ""))
    return float(m.group().replace(",", ".")) if m else None


def _unit(raw):
    u = str(raw or "").strip().lower()
    return UNIT_ALIASES.get(u, u[:20])


def _convert(value, unit, to):
    if unit == to or not unit or not to:
        return value
    if unit == "lb" and to == "kg":
        return value * KG_PER_LB
    if unit == "kg" and to == "lb":
        return value / KG_PER_LB
    return value


def _error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


@csrf_exempt   # called by a Shortcut with a personal key, never by a browser session
def metric_entries(request):
    if request.method != "POST":
        return _error("Use POST.", 405)
    user = _user_for(request)
    if user is None:
        return _error("Missing or wrong personal key. Make a new one on the Connect Apple Health page.", 401)
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return _error("The body isn't valid JSON.")
        if not isinstance(data, dict):
            return _error("Send a JSON object.")
    else:
        data = request.POST

    name = " ".join(str(data.get("metric") or "Weight").split())[:60] or "Weight"
    value = _number(data.get("value"))
    if value is None or not (0 < value < 10000):
        return _error("Send a positive number as value.")
    unit = _unit(data.get("unit")) or _unit(re.sub(r"[-\d.,\s]+", "", str(data.get("value") or "")))

    recorded_at = timezone.now()
    if data.get("recorded_at"):
        parsed = parse_datetime(str(data["recorded_at"]).strip())
        if parsed is None:
            return _error("recorded_at must be a date and time like 2026-11-26T07:45:00+05:30.")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        if parsed > timezone.now() + timedelta(days=1):
            return _error("recorded_at is in the future.")
        recorded_at = parsed

    metric = Metric.objects.filter(user=user, name__iexact=name).first()
    created_metric = metric is None
    if created_metric:
        metric = Metric.objects.create(user=user, name=name, unit=unit or ("kg" if name.lower() == "weight" else ""))
    value = round(_convert(value, unit, _unit(metric.unit)), 2)   # scales show 0.05 kg / 0.1 lb steps

    window = timedelta(seconds=SAME_ENTRY_WINDOW)
    same = metric.entries.filter(recorded_at__range=(recorded_at - window, recorded_at + window),
                                 value__gte=value - 0.001, value__lte=value + 0.001).first()
    entry = same or MetricEntry.objects.create(metric=metric, value=value, recorded_at=recorded_at, note="Apple Health")
    shown = f"{value:g}{(' ' + metric.unit) if metric.unit else ''}"
    return JsonResponse({
        "ok": True, "created": same is None, "created_metric": created_metric,
        "metric": metric.name, "value": value, "unit": metric.unit,
        "recorded_at": timezone.localtime(entry.recorded_at).isoformat(),
        "message": (f"Saved {shown} to {metric.name}." if same is None else f"{shown} was already saved."),
    }, status=201 if same is None else 200)


@login_required
def health_connect(request):
    """Page that makes / revokes the personal key and explains the Shortcut."""
    if request.method == "POST":
        if request.POST.get("action") == "revoke":
            PersonalKey.objects.filter(user=request.user).delete()
            request.session["health_notice"] = "Key removed. Shortcuts using it will stop working."
        else:
            request.session["health_new_key"] = new_key(request.user)
        return redirect("todolist:health_connect")
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])
    origin = settings.PUBLIC_ORIGIN.rstrip("/") or f"{request.scheme}://{request.get_host()}"
    return render(request, "todolist/health_connect.html", {
        "key": PersonalKey.objects.filter(user=request.user).first(),
        "new_key": request.session.pop("health_new_key", None),     # shown once
        "notice": request.session.pop("health_notice", None),
        "endpoint": origin + reverse("todolist:api_metric_entries"),
        "weight": Metric.objects.filter(user=request.user, name__iexact="weight").first(),
    })
