"""Install-to-Home-Screen (manifest, service worker) and the Notifications page."""
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from . import push
from .models import NotificationSettings, PushSubscription


@cache_control(no_cache=True, max_age=0)
def service_worker(request):
    js = render_to_string("todolist/sw.js", {
        "icon": static("todolist/icons/icon-192.png"), "badge": static("todolist/icons/badge-96.png"),
        "home": reverse("todolist:index")})
    res = HttpResponse(js, content_type="application/javascript; charset=utf-8")
    res["Service-Worker-Allowed"] = "/todolist/"
    return res


@cache_control(max_age=3600)
def manifest(request):
    home = reverse("todolist:index")
    data = {
        "name": "Todo list", "short_name": "Todo", "id": home, "start_url": home, "scope": home,
        "display": "standalone", "background_color": "#ffffff", "theme_color": "#146c43",
        "icons": [
            {"src": static("todolist/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("todolist/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("todolist/icons/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")


class NotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = NotificationSettings
        fields = ["due_reminders", "lead_minutes", "daily_summary", "summary_time"]
        widgets = {
            "due_reminders": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "lead_minutes": forms.Select(attrs={"class": "form-select"}),
            "daily_summary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "summary_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}, format="%H:%M"),
        }


def _settings_for(user):
    return NotificationSettings.objects.get_or_create(user=user)[0]


@login_required
def notifications(request):
    prefs = _settings_for(request.user)
    form = NotificationSettingsForm(request.POST or None, instance=prefs)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.session["notify_notice"] = "Saved."
        return redirect("todolist:notifications")
    return render(request, "todolist/notifications.html", {
        "form": form, "prefs": prefs, "enabled": push.enabled(), "public_key": push.public_key(),
        "devices": PushSubscription.objects.filter(user=request.user).order_by("-created_at"),
        "notice": request.session.pop("notify_notice", None),
    })


def _json(request):
    try:
        data = json.loads(request.body or b"{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


@login_required
@require_POST
def subscribe(request):
    data = _json(request)
    sub = data.get("subscription") or {}
    endpoint, keys = sub.get("endpoint", ""), sub.get("keys") or {}
    if not (isinstance(endpoint, str) and endpoint.startswith("https://") and len(endpoint) <= 1000
            and keys.get("p256dh") and keys.get("auth")):
        return JsonResponse({"ok": False, "error": "That doesn't look like a push subscription."}, status=400)
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        "user": request.user, "p256dh": str(keys["p256dh"])[:200], "auth": str(keys["auth"])[:100],
        "device": str(data.get("device") or "")[:80], "failures": 0})
    tz = str(data.get("timezone") or "")
    try:
        ZoneInfo(tz)
        NotificationSettings.objects.update_or_create(user=request.user, defaults={"timezone": tz})
    except (ZoneInfoNotFoundError, ValueError):
        _settings_for(request.user)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def unsubscribe(request):
    endpoint = _json(request).get("endpoint", "")
    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"ok": True})


@login_required
def remove_device(request, id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    PushSubscription.objects.filter(user=request.user, id=id).delete()
    request.session["notify_notice"] = "Device removed."
    return redirect("todolist:notifications")


@login_required
@require_POST
def test(request):
    n = push.send(request.user, "Notifications are on 🎉", "This is how reminders will look.", tag="test")
    return JsonResponse({"ok": n > 0, "sent": n})
