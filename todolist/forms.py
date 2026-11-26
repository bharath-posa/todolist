from django import forms

from .models import CustomUser, Item, Metric, MetricEntry, Project, split_tags

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class ItemForm(forms.ModelForm):
    """Add a task. The same fields (plus "done") are used for editing."""

    class Meta:
        model = Item
        fields = ["todo_item", "project", "start_date", "due_date", "itemPriority", "recurrence", "tags",
                  "pomodoro_estimate", "pomodoro_completed", "autoCompletePomodoro"]
        labels = {
            "todo_item": "Task",
            "project": "Project",
            "start_date": "Starts",
            "due_date": "Due",
            "itemPriority": "Priority",
            "recurrence": "Repeats",
            "tags": "Tags",
            "pomodoro_estimate": "Pomodoros planned",
            "pomodoro_completed": "Pomodoros done",
            "autoCompletePomodoro": "Mark done when all planned pomodoros are finished",
        }
        help_texts = {
            "tags": "Separate tags with commas, e.g. home, health.",
            "recurrence": "Repeating tasks start over (not done, 0 pomodoros) each period.",
        }
        widgets = {
            "todo_item": forms.Textarea(attrs={"rows": 3, "class": "form-control", "placeholder": "What needs doing?"}),
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}, format=DATETIME_FORMAT),
            "due_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}, format=DATETIME_FORMAT),
            "itemPriority": forms.Select(attrs={"class": "form-select"}),
            "project": forms.Select(attrs={"class": "form-select"}),
            "recurrence": forms.Select(attrs={"class": "form-select"}),
            "tags": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. home, health", "maxlength": 100}),
            "pomodoro_estimate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 99}),
            "pomodoro_completed": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 99}),
            "autoCompletePomodoro": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the signed-in user's own, active projects can be picked.
        projects = Project.objects.filter(user=user, archived=False) if user is not None else Project.objects.none()
        if self.instance and self.instance.project_id:
            projects = projects | Project.objects.filter(pk=self.instance.project_id, user=user)
        self.fields["project"].queryset = projects
        self.fields["project"].required = False
        self.fields["project"].empty_label = "No project"
        for name in ("start_date", "due_date"):
            self.fields[name].input_formats = [DATETIME_FORMAT, "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
        self.fields["start_date"].required = False
        self.fields["pomodoro_estimate"].initial = 3
        self.fields["pomodoro_completed"].initial = 0
        self.fields["itemPriority"].initial = 2

    def clean_tags(self):
        tags, seen = [], set()
        for tag in split_tags(self.cleaned_data.get("tags")):
            if tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag[:30])
        joined = ", ".join(tags)
        if len(joined) > 100:
            raise forms.ValidationError("Too many tags (100 characters at most).")
        return joined

    def clean(self):
        data = super().clean()
        start, due = data.get("start_date"), data.get("due_date")
        if start and due and due < start:
            self.add_error("due_date", "The due date can't be before the start.")
        for name in ("pomodoro_estimate", "pomodoro_completed"):
            if data.get(name) is not None and data[name] < 0:
                self.add_error(name, "Can't be negative.")
        return data


class ItemUpdateForm(ItemForm):
    class Meta(ItemForm.Meta):
        fields = ItemForm.Meta.fields + ["status"]
        labels = {**ItemForm.Meta.labels, "status": "Done"}
        widgets = {**ItemForm.Meta.widgets, "status": forms.CheckboxInput(attrs={"class": "form-check-input"})}


class CustomUserForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = "__all__"


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "archived"]
        labels = {"archived": "Archived (hidden from the task form)"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "maxlength": 80, "placeholder": "e.g. Move house"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "archived": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Project.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("You already have a project with this name.")
        return name


class MetricForm(forms.ModelForm):
    class Meta:
        model = Metric
        fields = ["name", "unit"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "maxlength": 60, "placeholder": "e.g. Body weight"}),
            "unit": forms.TextInput(attrs={"class": "form-control", "maxlength": 20, "placeholder": "e.g. kg"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Metric.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("You already track a value with this name.")
        return name


class MetricEntryForm(forms.ModelForm):
    class Meta:
        model = MetricEntry
        fields = ["value", "recorded_at", "note"]
        labels = {"recorded_at": "When"}
        widgets = {
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "any"}),
            "recorded_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}, format=DATETIME_FORMAT),
            "note": forms.TextInput(attrs={"class": "form-control", "maxlength": 200, "placeholder": "Optional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recorded_at"].input_formats = [DATETIME_FORMAT, "%Y-%m-%d %H:%M", "%Y-%m-%d"]
