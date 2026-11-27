from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from .models import Item, DeleteItem, CustomUser, Project, RecurringItemStatus, PRIORITY_CHOICES, split_tags
from django import forms
from .forms import ItemForm, ItemUpdateForm, CustomUserForm
from django.shortcuts import redirect
from django.urls import reverse
from django.http import QueryDict, JsonResponse
from django.forms.models import model_to_dict
from django.contrib.auth.forms import UserCreationForm , AuthenticationForm
from django.contrib.auth import authenticate , login as loginUser , logout
import json
from django.contrib.auth.decorators import login_required
import datetime
from django.db.models import Q
from django.utils import timezone

from . import game
#from django.db.models import Item
# Create your views here.

@login_required
def index(request):
    user = request.user
    today = timezone.localdate()
    reset_recurring_items(user, today)
    items = Item.objects.filter(user=user).select_related('project')
    recurring_items = items.filter(recurring_task=True).order_by('status', '-itemPriority')
    completed_items = items.filter(status=True).order_by('-due_date')
    list_of_items = items.filter(recurring_task=False, status=False).order_by('due_date')
    # Today: unfinished tasks due today or overdue, plus repeating tasks not yet done this period.
    end_of_today = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
    today_items = (items.filter(status=False)
                   .filter(Q(recurring_task=True) | Q(due_date__lte=end_of_today))
                   .order_by('-itemPriority', 'due_date'))
    # Today is shown in two groups: one-off tasks whose due day has passed, then the rest.
    start_of_today = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
    overdue_items = today_items.filter(recurring_task=False, due_date__lt=start_of_today)
    due_today_items = today_items.exclude(id__in=overdue_items.values('id'))
    by_lower = {}
    for tags in items.values_list('tags', flat=True):
        for t in split_tags(tags):
            by_lower.setdefault(t.lower(), t)   # one entry per tag, ignoring case
    all_tags = [by_lower[k] for k in sorted(by_lower)]
    highlight = None
    hid = request.GET.get('added') or request.GET.get('updated')
    if hid and hid.isdigit():
        item = items.filter(id=int(hid)).first()
        if item:
            tabs = [name for name, qs in (("Today", today_items), ("Recurring", recurring_items),
                                          ("Unit", list_of_items), ("Completed", completed_items))
                    if qs.filter(id=item.id).exists()]
            labels = {"Today": "Today", "Recurring": "Repeating", "Unit": "One-off", "Completed": "Done"}
            highlight = {"id": item.id, "title": item.todo_item, "tabs": tabs,
                         "tab_labels": [labels[t] for t in tabs], "verb": "Added" if 'added' in request.GET else "Saved"}
    context = {
        'highlight': highlight,
        'today_items': today_items, 'overdue_items': overdue_items, 'due_today_items': due_today_items,
        'recurring_items': recurring_items, 'list_of_items': list_of_items,
        'completed_items': completed_items, 'logged_user': user.username, 'all_tags': all_tags,
        'priority_choices': PRIORITY_CHOICES, 'now': timezone.now(),
        'projects': Project.objects.filter(user=user, archived=False), 'active_nav': 'tasks',
    }
    return render(request, 'todolist/index.html', context)


def detail(request, item_id):
    task_item = get_object_or_404(Item, pk=item_id)
    return render(request, 'todolist/details.html', {'task_item': task_item})

def thanks(request):
    context = {}
    return  render(request, 'todolist/thanks.html', context)


def _back(request, item, flag):
    """After saving a task: return to ?next (same app only) or the task list, highlighting the task."""
    target = request.GET.get('next') or request.POST.get('next') or ''
    if not (target.startswith('/todolist/') and not target.startswith('//')):
        target = reverse('todolist:index')
    return redirect(f"{target.split('?')[0]}?{flag}={item.id}")


@login_required
def additem(request):
    if request.method == 'POST':
        form = ItemForm(request.POST, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.create_date = timezone.now()
            item.start_date = item.start_date or item.create_date
            item.status = False
            if item.recurrence != "none":
                item.last_reset = timezone.localdate()
            item.save()
            return _back(request, item, 'added')
    else:
        now = timezone.localtime().replace(second=0, microsecond=0)
        form = ItemForm(initial={'start_date': now, 'due_date': now + datetime.timedelta(days=1),
                                 'project': request.GET.get('project')}, user=request.user)
    if request.method != 'POST':
        text = (request.GET.get('text') or '').strip()[:700]   # carried over from the quick-add box
        if text:
            form.initial['todo_item'] = text
    return render(request, 'todolist/additem.html', {'form': form, 'title': 'New task', 'submit_label': 'Add task'})


QUICK_ADD_PRIORITY = 2   # "Not urgent, important", the same default as the full form


@login_required
def quick_add(request):
    """One-line add from the task list (#9): due at the end of today, default priority."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    text = ' '.join((request.POST.get('text') or '').split())[:700]
    if not text:
        return redirect('todolist:index')
    now = timezone.now()
    end_of_today = timezone.make_aware(datetime.datetime.combine(timezone.localdate(), datetime.time(23, 59)))
    item = Item.objects.create(user=request.user, todo_item=text, create_date=now, start_date=now,
                               due_date=end_of_today, status=False, pomodoro_estimate=0, pomodoro_completed=0,
                               recurring_task=False, autoCompletePomodoro=False, itemPriority=QUICK_ADD_PRIORITY)
    return _back(request, item, 'added')


@login_required
def edit_item(request, id):
    item = get_object_or_404(Item, id=id, user=request.user)
    if request.method == "POST":
        was_recurring, was_done = item.recurrence, item.status
        form = ItemUpdateForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            if item.recurrence != "none" and (was_recurring == "none" or item.last_reset is None):
                item.last_reset = timezone.localdate()
            item.save()
            game.status_changed(item, was_done, item.status)
            return _back(request, item, 'updated')
    else:
        form = ItemUpdateForm(instance=item, user=request.user)
    return render(request, 'todolist/editItem.html', {'form': form, 'title': 'Edit task', 'submit_label': 'Save changes', 'item': item})


@login_required
def update_item_status(request):
    if request.method != 'POST':
        return JsonResponse({"ok": False}, status=405)
    item_id = int(QueryDict(request.body)['id'])
    item = get_object_or_404(Item, id=item_id, user=request.user)
    was_done = item.status
    Item.objects.filter(pk=item.pk, user=request.user).update(status=not was_done)
    game.status_changed(item, was_done, not was_done)
    return JsonResponse({"ok": True, "status": not was_done})


@login_required
def deleteItem(request,id):

    item_id = id
    if item_id :
            # saving the deleted item in deleted table 
        user = request.user
        deleted_item = get_object_or_404(Item, id=item_id, user=request.user)
        deleteObj = DeleteItem(
                               user=request.user,
                               todo_item=deleted_item.todo_item, 
                               create_date=deleted_item.create_date, 
                               start_date=deleted_item.start_date,
                               due_date=deleted_item.due_date, 
                               status=deleted_item.status, 
                               recurring_task=deleted_item.recurring_task,
                               pomodoro_estimate=deleted_item.pomodoro_estimate,
                               pomodoro_completed=deleted_item.pomodoro_completed,
                               itemPriority=deleted_item.itemPriority,
                               autoCompletePomodoro=deleted_item.autoCompletePomodoro,
                               tags=deleted_item.tags
                               )
        #deleteObj = DeletedItem(deleted_item)
        deleteObj.save()
        # delete it from items table 
        Item.objects.filter(pk=item_id, user=request.user).delete()
        return redirect('/todolist/')

@login_required
def pomodoroTimer(request,id):
    item_id = id
    if item_id :
            # saving the deleted item in deleted table 
        pomodoro_item = get_object_or_404(Item, id=item_id, user=request.user)

    from . import push
    return render(request, "todolist/pomodorotimer.html", {
        'item': pomodoro_item,
        'push_on': push.enabled() and request.user.push_subscriptions.exists(),
        'push_available': push.enabled()})

@login_required
def updatePomodoroCount(request):
    if request.method != 'POST':
        return JsonResponse({"ok": False}, status=405)
    item_id = QueryDict(request.body)['id']
    item = get_object_or_404(Item, id=item_id, user=request.user)
    count = item.pomodoro_completed + 1
    Item.objects.filter(pk=item.pk, user=request.user).update(pomodoro_completed=count)
    game.record_pomodoro(item)
    if item.autoCompletePomodoro and item.pomodoro_estimate == count and not item.status:
        Item.objects.filter(pk=item.pk, user=request.user).update(status=True)
        game.record_task_done(item)
    RecurringItemStatus.objects.create(user=request.user, item_id=item.pk, pomodoro_estimated=item.pomodoro_estimate,
                                       pomodoro_completed=count, event_time=timezone.now())
    return JsonResponse({'id': item_id, 'pomdoro_completed': count})


def addUser(request):
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('todolist:login')
    return render(request, 'todolist/addUser.html', {
        'form': form, 'title': 'Create an account', 'submit_label': 'Create account',
        'switch_text': 'Already have an account?', 'switch_link': 'Sign in', 'switch_url': reverse('todolist:login')})


def login(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        loginUser(request, form.get_user())
        next_url = request.GET.get('next', '')
        if next_url.startswith('/todolist/') and not next_url.startswith('//'):
            return redirect(next_url)
        return redirect('todolist:index')
    return render(request, 'todolist/login.html', {
        'form': form, 'title': 'Sign in', 'submit_label': 'Sign in',
        'switch_text': 'New here?', 'switch_link': 'Create an account', 'switch_url': reverse('todolist:addUser')})


@login_required
def signout(request):
    logout(request)
    return redirect('todolist:login')


def reset_recurring_items(user, today):
    """Start this user's repeating tasks over when their day/week/month/year has rolled over."""
    for item in Item.objects.filter(user=user).exclude(recurrence="none"):
        item.reset_if_new_period(today)


'''
def mappingTelegrambotUser():
    # Get Todays Date
'''
