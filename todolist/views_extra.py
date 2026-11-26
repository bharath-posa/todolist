"""Projects (#57), tracked values (#34) and the Insights page (#35, #36)."""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import game
from .forms import MetricEntryForm, MetricForm, ProjectForm
from .models import PRIORITY_CHOICES, Activity, Item, Metric, MetricEntry, Project


# ---------- projects ----------

def _with_progress(projects):
    return projects.annotate(total=Count("items"), done=Count("items", filter=Q(items__status=True)))


@login_required
def projects(request):
    items = _with_progress(Project.objects.filter(user=request.user))
    unassigned = Item.objects.filter(user=request.user, project__isnull=True).aggregate(
        total=Count("id"), done=Count("id", filter=Q(status=True)))
    return render(request, "todolist/projects.html", {"projects": items, "unassigned": unassigned})


@login_required
def project_edit(request, id=None):
    project = get_object_or_404(Project, id=id, user=request.user) if id else None
    form = ProjectForm(request.POST or None, instance=project, user=request.user)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.user = request.user
        project.save()
        return redirect("todolist:projects")
    return render(request, "todolist/project_form.html", {
        "form": form, "project": project, "title": "Edit project" if project else "New project",
        "submit_label": "Save changes" if project else "Create project"})


@login_required
def project_delete(request, id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    project = get_object_or_404(Project, id=id, user=request.user)
    project.delete()  # its tasks stay, without a project
    return redirect("todolist:projects")


# ---------- tracked values ----------

@login_required
def metrics(request):
    form = MetricForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        metric = form.save(commit=False)
        metric.user = request.user
        metric.save()
        return redirect("todolist:metric", id=metric.id)
    rows = []
    for m in Metric.objects.filter(user=request.user).annotate(n=Count("entries")):
        latest = m.entries.first()
        rows.append({"metric": m, "count": m.n, "latest": latest})
    return render(request, "todolist/metrics.html", {"rows": rows, "form": form})


@login_required
def metric(request, id):
    metric = get_object_or_404(Metric, id=id, user=request.user)
    form = MetricEntryForm(request.POST or None, initial={"recorded_at": timezone.localtime().replace(second=0, microsecond=0)})
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.metric = metric
        entry.save()
        return redirect("todolist:metric", id=metric.id)
    entries = list(metric.entries.all()[:500])
    chart = {
        "labels": [timezone.localtime(e.recorded_at).strftime("%d %b %Y") for e in reversed(entries)],
        "values": [e.value for e in reversed(entries)],
        "unit": metric.unit,
    }
    values = [e.value for e in entries]
    summary = None
    if values:
        summary = {"latest": values[0], "first": values[-1], "change": values[0] - values[-1],
                   "low": min(values), "high": max(values)}
    return render(request, "todolist/metric.html", {"metric": metric, "form": form, "entries": entries,
                                                    "chart": chart, "summary": summary})


@login_required
def metric_delete(request, id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    get_object_or_404(Metric, id=id, user=request.user).delete()
    return redirect("todolist:metrics")


@login_required
def entry_delete(request, id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    entry = get_object_or_404(MetricEntry, id=id, metric__user=request.user)
    metric_id = entry.metric_id
    entry.delete()
    return redirect("todolist:metric", id=metric_id)


# ---------- insights ----------

@login_required
def insights(request):
    user = request.user
    by_priority = dict(Activity.objects.filter(user=user, kind=Activity.TASK_DONE)
                       .values_list("priority").annotate(n=Count("id")).values_list("priority", "n"))
    open_by_priority = dict(Item.objects.filter(user=user, status=False)
                            .values_list("itemPriority").annotate(n=Count("id")).values_list("itemPriority", "n"))
    priority_chart = {
        "labels": [label for _, label in PRIORITY_CHOICES],
        "done": [by_priority.get(v, 0) for v, _ in PRIORITY_CHOICES],
        "open": [open_by_priority.get(v, 0) for v, _ in PRIORITY_CHOICES],
    }
    return render(request, "todolist/insights.html", {
        "stats": game.stats(user),
        "series": game.daily_series(user, days=30),
        "priority_chart": priority_chart,
        "projects": _with_progress(Project.objects.filter(user=user, archived=False)),
        "recent": Activity.objects.filter(user=user)[:10],
    })
