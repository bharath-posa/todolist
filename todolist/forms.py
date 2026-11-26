from django import forms

from .models import CustomUser, Item, split_tags

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class ItemForm(forms.ModelForm):
    """Add a task. The same fields (plus "done") are used for editing."""

    class Meta:
        model = Item
        fields = ["todo_item", "start_date", "due_date", "itemPriority", "recurrence", "tags",
                  "pomodoro_estimate", "pomodoro_completed", "autoCompletePomodoro"]
        labels = {
            "todo_item": "Task",
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
            "recurrence": forms.Select(attrs={"class": "form-select"}),
            "tags": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. home, health", "maxlength": 100}),
            "pomodoro_estimate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 99}),
            "pomodoro_completed": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 99}),
            "autoCompletePomodoro": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
