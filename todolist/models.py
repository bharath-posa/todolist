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
        Item.objects.filter(pk=self.pk).update(status=False, pomodoro_completed=0, last_reset=today)
        self.status, self.pomodoro_completed, self.last_reset = False, 0, today
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
