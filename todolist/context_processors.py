from . import game


def player(request):
    """Level and points for the navigation bar on every signed-in page."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    s = game.stats(request.user)
    return {"player": {"level": s["level"], "points": s["points"], "streak": s["streak"]}}
