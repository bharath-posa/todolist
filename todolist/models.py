from django.db import models
from django.utils import timezone
import datetime
from django.contrib.auth.models import User

class CustomUser(models.Model):
    username = models.CharField(max_length=70)
    password = models.CharField(max_length=50)
    email = models.EmailField()
    profile_name = models.CharField(max_length=70)
    def __str__(self):
        return self.username


PRIORITY_CHOICES = [
    (1, "Not urgent, not important"),
    (2, "Not urgent, important"),
    (3, "Urgent, not important"),
    (4, "Urgent, important"),
]

RECURRENCE_CHOICES = [
    ("none", "Does not repeat"),
    ("daily", "Every day"),
    ("weekly", "Every week"),
    ("monthly", "Every month"),
    ("yearly", "Every year"),
]


def period_key(recurrence, day):
    """Identifies the repeat period that `day` falls in; a new key means the task resets."""
    if recurrence == "daily":
        return day.isoformat()
    if recurrence == "weekly":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week}"
    if recurrence == "monthly":
        return f"{day.year}-{day.month}"
    if recurrence == "yearly":
        return str(day.year)
    return None


def split_tags(text):
    return [t.strip() for t in (text or "").split(",") if t.strip()]


# Create your models here
# .
class Item(models.Model):
    # create  a list item todo
    # user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    user  = models.ForeignKey(User, on_delete= models.CASCADE)
    todo_item = models.CharField(max_length=700)
    create_date = models.DateTimeField('Date created')
    start_date = models.DateTimeField('Date started',null=True)
    due_date = models.DateTimeField('Due date')
    status = models.BooleanField('Completed')
    pomodoro_estimate = models.IntegerField('Pomodoro Estimate')
    pomodoro_completed = models.IntegerField('Pomodoro Completed')
    recurring_task = models.BooleanField('Recurring')
    autoCompletePomodoro = models.BooleanField('Auto Pomodoro Complete')
    itemPriority = models.IntegerField('priority', choices=PRIORITY_CHOICES)
    tags = models.CharField(max_length=100, blank=True, default="")
    recurrence = models.CharField('Repeats', max_length=10, choices=RECURRENCE_CHOICES, default="none")
    last_reset = models.DateField('Last reset', null=True, blank=True)
    project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    completed_at = models.DateTimeField('Finished at', null=True, blank=True)

    def save(self, *args, **kwargs):
        # recurring_task is kept for existing queries; recurrence is the source of truth.
        self.recurring_task = self.recurrence != "none"
        super().save(*args, **kwargs)

    @property
    def tag_list(self):
        return split_tags(self.tags)

    def reset_if_new_period(self, today):
        """Start a repeating task over (not done, 0 pomodoros) when its period rolls over.
        Returns True if it was reset."""
        if self.recurrence == "none":
            return False
        if self.last_reset is None:
            Item.objects.filter(pk=self.pk).update(last_reset=today)
            self.last_reset = today
            return False
        if period_key(self.recurrence, self.last_reset) == period_key(self.recurrence, today):
            return False
        Item.objects.filter(pk=self.pk).update(status=False, pomodoro_completed=0, last_reset=today, completed_at=None)
        self.status, self.pomodoro_completed, self.last_reset, self.completed_at = False, 0, today, None
        return True

    def __str__(self):
        return self.todo_item

# Create your models here.
class DeleteItem(models.Model):
    # create  a list item todo
    # user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    user  = models.ForeignKey(User, on_delete= models.CASCADE)
    todo_item = models.CharField(max_length=700)
    create_date = models.DateTimeField('Date created')
    start_date = models.DateTimeField('Date started',null=True)
    due_date = models.DateTimeField('Due date')
    status = models.BooleanField('Completed')
    pomodoro_estimate = models.IntegerField('Pomodoro Estimate')
    pomodoro_completed = models.IntegerField('Pomodoro Completed')
    recurring_task = models.BooleanField('Recurring')
    autoCompletePomodoro = models.BooleanField(' Auto Pomodoro Complete')
    itemPriority = models.IntegerField('priority')
    tags = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return self.todo_item



class dateStatusCheck(models.Model):
    today_date = models.DateField('Today Date')
    def __str__(self):
        return self.today_date.strftime('%Y-%m-%d')


class RecurringItemStatus(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user')
    #item_id = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='todo_item_recur')
    item_id = models.IntegerField('Item')
    pomodoro_completed = models.IntegerField('Pomodoro Completed')
    pomodoro_estimated = models.IntegerField('Pomodoro Estimate')
    event_time  = models.DateTimeField('Event Timestamp')
    def __str__(self):
        return self.todo_item


class telegrambotUserMapping(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    telebotId = models.TextField('telegramId')
    event_time = models.DateTimeField('Event Timestamp')


# Colour dots for projects (#16): picked from the id so they stay stable without a database field.
PROJECT_COLORS = ["#2f9e44", "#1c7ed6", "#e8590c", "#ae3ec9", "#0c8599", "#d6336c", "#f08c00", "#5c7cfa"]


class Project(models.Model):
    """A group of tasks (#57)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True, default="")
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['archived', 'name']
        constraints = [models.UniqueConstraint(fields=['user', 'name'], name='unique_project_name_per_user')]

    def __str__(self):
        return self.name

    @property
    def color(self):
        return PROJECT_COLORS[(self.pk or 0) % len(PROJECT_COLORS)]


class Activity(models.Model):
    """Something worth points (#36): a task finished or a pomodoro completed."""
    TASK_DONE, POMODORO = "task_done", "pomodoro"
    KIND_CHOICES = [(TASK_DONE, "Task finished"), (POMODORO, "Pomodoro completed")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    item_id = models.IntegerField(null=True, blank=True)
    priority = models.IntegerField(null=True, blank=True)
    points = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'created_at'])]


class Metric(models.Model):
    """A value you track over time, e.g. body weight (#34)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='metrics')
    name = models.CharField(max_length=60)
    unit = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['user', 'name'], name='unique_metric_name_per_user')]

    def __str__(self):
        return self.name


class MetricEntry(models.Model):
    metric = models.ForeignKey(Metric, on_delete=models.CASCADE, related_name='entries')
    value = models.FloatField()
    recorded_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ['-recorded_at']


# ---------- notifications ----------

class PushSubscription(models.Model):
    """One device (browser or Home Screen app) that allowed notifications."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    device = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.user} · {self.device or 'device'}"


LEAD_CHOICES = [(0, "When it's due"), (15, "15 minutes before"), (60, "1 hour before"), (1440, "1 day before")]


class NotificationSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_settings')
    timezone = models.CharField(max_length=64, default="UTC")
    due_reminders = models.BooleanField("Remind me about due tasks", default=True)
    lead_minutes = models.PositiveIntegerField("When", choices=LEAD_CHOICES, default=15)
    daily_summary = models.BooleanField("Morning summary", default=True)
    summary_time = models.TimeField("At", default=datetime.time(8, 0))

    def __str__(self):
        return f"{self.user} notifications"


TIMER_MODES = [("pomodoro", "Pomodoro"), ("short", "Short break"), ("long", "Long break")]


class TimerAlarm(models.Model):
    """The running pomodoro timer's end time, so a push can sound the alarm even if the page is asleep.
    One per user: starting a timer replaces it; pausing, stopping or resetting removes it."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='timer_alarm')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    mode = models.CharField(max_length=10, choices=TIMER_MODES, default="pomodoro")
    ends_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} timer until {self.ends_at:%H:%M:%S}"


class SentNotification(models.Model):
    """Remembers what was sent so a reminder or summary never goes out twice."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    kind = models.CharField(max_length=20)
    key = models.CharField(max_length=100)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'kind', 'key'], name='notification_sent_once')]
