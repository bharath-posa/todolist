import datetime

from django.db.models import Count, Q
from django.utils import timezone

from . import game
from .models import Item, Project


def player(request):
    """Level and points for the top bar, and the lists for the desktop sidebar, on every signed-in page."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    user = request.user
    s = game.stats(user)
    end_of_today = timezone.make_aware(datetime.datetime.combine(timezone.localdate(), datetime.time.max))
    today_count = Item.objects.filter(user=user, status=False).filter(
        Q(recurring_task=True) | Q(due_date__lte=end_of_today)).count()
    projects = (Project.objects.filter(user=user, archived=False)
                .annotate(open_count=Count("items", filter=Q(items__status=False))))
    return {
        "player": {"level": s["level"], "points": s["points"], "streak": s["streak"]},
        "sidebar": {"today_count": today_count, "projects": projects},
    }
