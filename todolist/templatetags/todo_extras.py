"""Small display helpers for task rows (#13)."""
import datetime

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def due_label(value):
    """'Today', 'Tomorrow', 'Yesterday', a weekday within the next week, else '26 Nov' (with the year if not this year)."""
    if not value:
        return ""
    day = timezone.localtime(value).date()
    today = timezone.localdate()
    delta = (day - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    if 1 < delta < 7:
        return day.strftime("%A")
    if day.year == today.year:
        return f"{day.day} {day.strftime('%b')}"
    return f"{day.day} {day.strftime('%b %Y')}"


@register.filter
def is_overdue(item):
    """A one-off task, not done, whose due day has passed."""
    if item.status or item.recurring_task or not item.due_date:
        return False
    return timezone.localtime(item.due_date).date() < timezone.localdate()
