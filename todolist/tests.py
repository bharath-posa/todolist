import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import DeleteItem, Item, period_key


def make_item(user, **kw):
    now = timezone.now()
    fields = dict(todo_item="Water the plants", create_date=now, start_date=now, due_date=now + datetime.timedelta(days=1),
                  status=False, pomodoro_estimate=3, pomodoro_completed=0, recurring_task=False,
                  autoCompletePomodoro=False, itemPriority=2, tags="")
    fields.update(kw)
    return Item.objects.create(user=user, **fields)


class Base(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="Cobalt-Fern-482")
        self.bob = User.objects.create_user("bob", password="Cobalt-Fern-482")
        self.item = make_item(self.alice)

    def login(self, user):
        self.client.force_login(user)


class LoginRedirects(Base):
    def test_anonymous_pages_redirect_to_login(self):
        for path in ("/todolist/", "/todolist/additem/", f"/todolist/editItem/{self.item.id}"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 302, path)
            self.assertTrue(res["Location"].startswith("/todolist/login/"), res["Location"])


class Ownership(Base):
    def test_owner_can_open_edit_and_timer(self):
        self.login(self.alice)
        self.assertEqual(self.client.get(f"/todolist/editItem/{self.item.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/todolist/pomodorotimer/{self.item.id}").status_code, 200)

    def test_other_user_gets_404_everywhere(self):
        self.login(self.bob)
        for path in (f"/todolist/editItem/{self.item.id}", f"/todolist/deleteItem/{self.item.id}",
                     f"/todolist/pomodorotimer/{self.item.id}"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        res = self.client.post("/todolist/ajax/update_item_status", f"id={self.item.id}",
                               content_type="application/x-www-form-urlencoded")
        self.assertEqual(res.status_code, 404)
        res = self.client.post("/todolist/pomodorotimer/ajax/updatepomodoro", f"id={self.item.id}",
                               content_type="application/x-www-form-urlencoded")
        self.assertEqual(res.status_code, 404)
        self.assertTrue(Item.objects.filter(id=self.item.id, status=False, pomodoro_completed=0).exists())

    def test_edit_cannot_reassign_owner(self):
        self.login(self.alice)
        self.client.post(f"/todolist/editItem/{self.item.id}", {
            "user": self.bob.id, "todo_item": "Renamed", "start_date": "2026-01-01 09:00", "due_date": "2026-01-02 09:00",
            "pomodoro_estimate": 2, "pomodoro_completed": 0, "itemPriority": 3, "recurrence": "none"})
        self.item.refresh_from_db()
        self.assertEqual((self.item.user_id, self.item.todo_item), (self.alice.id, "Renamed"))

    def test_home_lists_only_own_items(self):
        make_item(self.bob, todo_item="Bob's secret task")
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        self.assertIn("Water the plants", body)
        self.assertNotIn("Bob's secret task", body)


class Issue56DeleteWithPomodoros(Base):
    def test_delete_item_with_several_completed_pomodoros(self):
        item = make_item(self.alice, pomodoro_completed=4, autoCompletePomodoro=True)
        self.login(self.alice)
        res = self.client.get(f"/todolist/deleteItem/{item.id}")
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Item.objects.filter(id=item.id).exists())
        archived = DeleteItem.objects.get(todo_item=item.todo_item, user=self.alice)
        self.assertTrue(archived.autoCompletePomodoro)
        self.assertEqual(archived.pomodoro_completed, 4)


class Issue47CompletedPriority(Base):
    def test_completed_tab_shows_priority(self):
        make_item(self.alice, todo_item="Done thing", status=True, itemPriority=4)
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        completed = body[body.index('id="Completed"'):]
        self.assertIn("prio-4", completed)
        self.assertIn("Urgent, important", completed)


class SafeMarkup(Base):
    def test_task_text_is_not_placed_in_javascript(self):
        make_item(self.alice, todo_item="x');alert(1);('")
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        self.assertNotIn("toggle_status(", body)          # ticking is wired up in app.js, not inline
        self.assertIn("x&#x27;);alert(1);(&#x27;", body)   # the text only appears escaped


class FreshDatabase(Base):
    def test_home_works_without_daily_marker_row(self):
        self.login(self.alice)
        self.assertEqual(self.client.get("/todolist/").status_code, 200)


class StatusToggle(Base):
    def test_owner_toggles_status(self):
        self.login(self.alice)
        res = self.client.post("/todolist/ajax/update_item_status", f"id={self.item.id}",
                               content_type="application/x-www-form-urlencoded")
        self.assertEqual(res.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.status)


FORM = {"todo_item": "Stretch", "start_date": "2026-03-01T08:00", "due_date": "2026-03-01T09:00",
        "itemPriority": 3, "recurrence": "none", "tags": "", "pomodoro_estimate": 2, "pomodoro_completed": 0}


class AddAndEditForms(Base):
    def test_add_task_with_tags_and_recurrence(self):
        self.login(self.alice)
        res = self.client.post("/todolist/additem/", {**FORM, "tags": "health,  Home, health ,", "recurrence": "weekly"})
        self.assertEqual(res.status_code, 302)
        item = Item.objects.get(todo_item="Stretch")
        self.assertEqual((item.user, item.tags, item.recurrence, item.recurring_task), (self.alice, "health, Home", "weekly", True))
        self.assertIsNotNone(item.last_reset)

    def test_add_form_rejects_due_before_start(self):
        self.login(self.alice)
        res = self.client.post("/todolist/additem/", {**FORM, "due_date": "2026-02-01T09:00"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "can&#x27;t be before the start")
        self.assertFalse(Item.objects.filter(todo_item="Stretch").exists())

    def test_edit_marks_done_and_changes_repeat(self):
        self.login(self.alice)
        res = self.client.post(f"/todolist/editItem/{self.item.id}", {**FORM, "status": "on", "recurrence": "monthly"})
        self.assertEqual(res.status_code, 302)
        self.item.refresh_from_db()
        self.assertTrue(self.item.status)
        self.assertEqual(self.item.recurrence, "monthly")
        self.assertTrue(self.item.recurring_task)

    def test_pages_render(self):
        self.login(self.alice)
        self.assertContains(self.client.get("/todolist/additem/"), "Repeats")
        self.assertContains(self.client.get(f"/todolist/editItem/{self.item.id}"), "Water the plants")


class Recurrence(TestCase):
    def test_period_keys(self):
        d = datetime.date
        self.assertNotEqual(period_key("daily", d(2026, 1, 1)), period_key("daily", d(2026, 1, 2)))
        self.assertEqual(period_key("weekly", d(2026, 1, 5)), period_key("weekly", d(2026, 1, 11)))   # Mon..Sun
        self.assertNotEqual(period_key("weekly", d(2026, 1, 11)), period_key("weekly", d(2026, 1, 12)))
        self.assertEqual(period_key("monthly", d(2026, 1, 1)), period_key("monthly", d(2026, 1, 31)))
        self.assertNotEqual(period_key("monthly", d(2026, 1, 31)), period_key("monthly", d(2026, 2, 1)))
        self.assertEqual(period_key("yearly", d(2026, 1, 1)), period_key("yearly", d(2026, 12, 31)))
        self.assertIsNone(period_key("none", d(2026, 1, 1)))

    def test_reset_only_when_period_rolls_over(self):
        user = User.objects.create_user("carol")
        item = make_item(user, recurrence="monthly", status=True, pomodoro_completed=3,
                         last_reset=datetime.date(2026, 1, 10))
        self.assertFalse(item.reset_if_new_period(datetime.date(2026, 1, 31)))
        item.refresh_from_db(); self.assertTrue(item.status)
        self.assertTrue(item.reset_if_new_period(datetime.date(2026, 2, 1)))
        item.refresh_from_db()
        self.assertEqual((item.status, item.pomodoro_completed, item.last_reset), (False, 0, datetime.date(2026, 2, 1)))

    def test_home_resets_only_my_tasks(self):
        alice, bob = User.objects.create_user("a2"), User.objects.create_user("b2")
        old = timezone.localdate() - datetime.timedelta(days=2)
        mine = make_item(alice, recurrence="daily", status=True, last_reset=old)
        theirs = make_item(bob, recurrence="daily", status=True, last_reset=old)
        self.client.force_login(alice)
        self.client.get("/todolist/")
        mine.refresh_from_db(); theirs.refresh_from_db()
        self.assertFalse(mine.status)
        self.assertTrue(theirs.status)


class TodayAndTags(Base):
    def test_today_tab_contents(self):
        now = timezone.now()
        make_item(self.alice, todo_item="Due today", due_date=now)
        make_item(self.alice, todo_item="Overdue thing", due_date=now - datetime.timedelta(days=3))
        make_item(self.alice, todo_item="Next week", due_date=now + datetime.timedelta(days=7))
        make_item(self.alice, todo_item="Daily habit", recurrence="daily", due_date=now + datetime.timedelta(days=30),
                  last_reset=timezone.localdate())
        make_item(self.alice, todo_item="Already done", due_date=now, status=True)
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        today = body[body.index('id="Today"'):body.index('id="Recurring"')]
        for title in ("Due today", "Overdue thing", "Daily habit"):
            self.assertIn(title, today)
        for title in ("Next week", "Already done"):
            self.assertNotIn(title, today)
        self.assertIn("Overdue", today)

    def test_tag_filter_lists_my_tags_once(self):
        make_item(self.alice, todo_item="A", tags="home, Health")
        make_item(self.alice, todo_item="B", tags="health")
        make_item(self.bob, todo_item="C", tags="secret-bob-tag")
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        self.assertEqual(body.count('<option value="health">'), 1)
        self.assertIn('<option value="home">', body)
        self.assertNotIn("secret-bob-tag", body)

    def test_items_are_collapsible(self):
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        self.assertIn("<details>", body)
        self.assertIn("<summary>", body)


class AuthPages(TestCase):
    def test_signup_then_login_with_next(self):
        res = self.client.post("/todolist/adduser/", {"username": "erin", "password1": "Cobalt-Fern-482", "password2": "Cobalt-Fern-482"})
        self.assertEqual(res.status_code, 302)
        res = self.client.post("/todolist/login/?next=/todolist/additem/", {"username": "erin", "password": "Cobalt-Fern-482"})
        self.assertEqual(res["Location"], "/todolist/additem/")

    def test_wrong_password_shows_error(self):
        User.objects.create_user("fred", password="Cobalt-Fern-482")
        res = self.client.post("/todolist/login/", {"username": "fred", "password": "nope"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "alert-danger")

    def test_next_cannot_leave_the_app(self):
        User.objects.create_user("gina", password="Cobalt-Fern-482")
        res = self.client.post("/todolist/login/?next=https://evil.example/", {"username": "gina", "password": "Cobalt-Fern-482"})
        self.assertEqual(res["Location"], "/todolist/")


from . import game  # noqa: E402
from .models import Activity, Metric, MetricEntry, Project  # noqa: E402


class Projects(Base):
    def test_create_assign_and_progress(self):
        self.login(self.alice)
        res = self.client.post("/todolist/projects/new/", {"name": "  Move   house ", "description": "Boxes"})
        self.assertEqual(res.status_code, 302)
        project = Project.objects.get(user=self.alice)
        self.assertEqual(project.name, "Move house")
        self.client.post("/todolist/additem/", {**FORM, "project": project.id})
        item = Item.objects.get(todo_item="Stretch")
        self.assertEqual(item.project, project)
        Item.objects.filter(pk=item.pk).update(status=True)
        page = self.client.get("/todolist/projects/").content.decode()
        self.assertIn("1 of 1 done", page)

    def test_duplicate_name_rejected(self):
        Project.objects.create(user=self.alice, name="Garden")
        self.login(self.alice)
        res = self.client.post("/todolist/projects/new/", {"name": "garden"})
        self.assertContains(res, "already have a project")

    def test_cannot_use_or_touch_someone_elses_project(self):
        theirs = Project.objects.create(user=self.bob, name="Bob's")
        self.login(self.alice)
        res = self.client.post("/todolist/additem/", {**FORM, "project": theirs.id})
        self.assertEqual(res.status_code, 200)  # invalid choice
        self.assertFalse(Item.objects.filter(todo_item="Stretch").exists())
        self.assertEqual(self.client.get(f"/todolist/projects/{theirs.id}/edit/").status_code, 404)
        self.assertEqual(self.client.post(f"/todolist/projects/{theirs.id}/delete/").status_code, 404)
        self.assertNotContains(self.client.get("/todolist/"), "Bob&#x27;s")

    def test_delete_keeps_tasks(self):
        project = Project.objects.create(user=self.alice, name="Temp")
        Item.objects.filter(pk=self.item.pk).update(project=project)
        self.login(self.alice)
        self.assertEqual(self.client.get(f"/todolist/projects/{project.id}/delete/").status_code, 405)
        self.client.post(f"/todolist/projects/{project.id}/delete/")
        self.item.refresh_from_db()
        self.assertIsNone(self.item.project)


class Metrics(Base):
    def test_track_values(self):
        self.login(self.alice)
        res = self.client.post("/todolist/metrics/", {"name": "Body weight", "unit": "kg"})
        metric = Metric.objects.get(user=self.alice)
        self.assertRedirects(res, f"/todolist/metrics/{metric.id}/")
        for value, when in ((82.5, "2026-01-01T08:00"), (81.0, "2026-01-15T08:00")):
            self.client.post(f"/todolist/metrics/{metric.id}/", {"value": value, "recorded_at": when, "note": ""})
        page = self.client.get(f"/todolist/metrics/{metric.id}/")
        self.assertContains(page, "metric-chart")
        self.assertEqual(page.context["summary"]["change"], -1.5)
        self.assertEqual(page.context["chart"]["values"], [82.5, 81.0])

    def test_metrics_are_private(self):
        theirs = Metric.objects.create(user=self.bob, name="Bob weight")
        entry = MetricEntry.objects.create(metric=theirs, value=90)
        self.login(self.alice)
        self.assertEqual(self.client.get(f"/todolist/metrics/{theirs.id}/").status_code, 404)
        self.assertEqual(self.client.post(f"/todolist/metrics/entries/{entry.id}/delete/").status_code, 404)
        self.assertNotContains(self.client.get("/todolist/metrics/"), "Bob weight")


class Game(Base):
    def toggle(self, item):
        return self.client.post("/todolist/ajax/update_item_status", f"id={item.id}",
                                content_type="application/x-www-form-urlencoded")

    def test_points_for_done_and_taken_back_on_undo(self):
        item = make_item(self.alice, itemPriority=4)
        self.login(self.alice)
        self.toggle(item)
        self.assertEqual(game.stats(self.alice)["points"], 20)
        self.toggle(item)  # un-tick: points removed, no farming
        self.assertEqual(game.stats(self.alice)["points"], 0)
        item.refresh_from_db()
        self.assertIsNone(item.completed_at)

    def test_pomodoros_and_auto_complete(self):
        item = make_item(self.alice, itemPriority=2, pomodoro_estimate=2, autoCompletePomodoro=True)
        self.login(self.alice)
        for _ in range(2):
            self.client.post("/todolist/pomodorotimer/ajax/updatepomodoro", f"id={item.id}",
                             content_type="application/x-www-form-urlencoded")
        s = game.stats(self.alice)
        self.assertEqual((s["pomodoros"], s["tasks_done"], s["points"]), (2, 1, 2 * 2 + 10))
        item.refresh_from_db()
        self.assertTrue(item.status)

    def test_edit_marking_done_counts(self):
        self.login(self.alice)
        self.client.post(f"/todolist/editItem/{self.item.id}", {**FORM, "status": "on"})
        self.assertEqual(game.stats(self.alice)["tasks_done"], 1)

    def test_streaks_and_levels(self):
        today = datetime.date(2026, 3, 10)
        for days_ago in (0, 1, 2, 5, 6):
            when = timezone.make_aware(datetime.datetime.combine(today - datetime.timedelta(days=days_ago), datetime.time(12)))
            Activity.objects.create(user=self.alice, kind=Activity.TASK_DONE, points=40, created_at=when)
        s = game.stats(self.alice, today=today)
        self.assertEqual((s["streak"], s["best_streak"]), (3, 3))
        self.assertEqual((s["points"], s["level"], s["level_progress"]), (200, 3, 0))
        earned = {b["id"] for b in s["badges"] if b["earned"]}
        self.assertTrue({"first-task", "streak-3"} <= earned)
        self.assertNotIn("streak-7", earned)
        # yesterday still keeps the streak alive before doing anything today
        self.assertEqual(game.stats(self.alice, today=today + datetime.timedelta(days=1))["streak"], 3)
        self.assertEqual(game.stats(self.alice, today=today + datetime.timedelta(days=2))["streak"], 0)

    def test_insights_page_and_nav(self):
        self.login(self.alice)
        self.toggle(self.item)
        page = self.client.get("/todolist/insights/")
        self.assertContains(page, "daily-chart")
        self.assertEqual(page.context["series"]["tasks"][-1], 1)
        self.assertContains(self.client.get("/todolist/"), "Lv 1")


class SavedTaskIsEasyToFind(Base):
    """Regression: a task added under a project seemed to disappear (wrong tab, no project task list)."""

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(user=self.alice, name="Get fit")
        self.login(self.alice)

    def test_add_from_project_returns_to_project_page_with_the_task(self):
        url = f"/todolist/additem/?project={self.project.id}&next=/todolist/projects/{self.project.id}/"
        res = self.client.post(url, {**FORM, "project": self.project.id, "recurrence": "daily"})
        item = Item.objects.get(todo_item="Stretch")
        self.assertEqual(res["Location"], f"/todolist/projects/{self.project.id}/?added={item.id}")
        page = self.client.get(res["Location"])
        self.assertContains(page, 'data-highlight-id="%d"' % item.id)
        self.assertIn(item, page.context["open_items"])

    def test_add_from_home_names_the_tabs_it_landed_in(self):
        res = self.client.post("/todolist/additem/", {**FORM, "project": self.project.id, "recurrence": "daily"})
        item = Item.objects.get(todo_item="Stretch")
        self.assertEqual(res["Location"], f"/todolist/?added={item.id}")
        page = self.client.get(res["Location"])
        self.assertEqual(page.context["highlight"]["tabs"], ["Today", "Recurring"])
        self.assertContains(page, "under Today and Repeating")

    def test_next_outside_the_app_is_ignored(self):
        res = self.client.post("/todolist/additem/?next=https://evil.example/", FORM)
        self.assertTrue(res["Location"].startswith("/todolist/?added="))

    def test_project_page_is_private(self):
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(f"/todolist/projects/{self.project.id}/").status_code, 404)


class TabStyles(TestCase):
    """Regression: an old `.tabcontent { display: none }` rule hid every task list."""

    def test_stylesheet_does_not_hide_tab_panels(self):
        import re
        from django.contrib.staticfiles import finders
        css = open(finders.find("todolist/style.css")).read()
        for block in re.findall(r"\.tabcontent\s*\{([^}]*)\}", css):
            self.assertNotIn("display: none", block.replace("display:none", "display: none"))


class PhoneFirstHome(Base):
    """UI Tier 1 (#8-#12): quick add, folded filters, account menu, bottom bar, Overdue/Today groups."""

    def setUp(self):
        super().setUp()
        self.login(self.alice)

    def test_quick_add_creates_a_task_due_today_and_highlights_it(self):
        res = self.client.post("/todolist/quickadd/", {"text": "  Call   the dentist "})
        item = Item.objects.get(todo_item="Call the dentist")
        self.assertEqual(res["Location"], f"/todolist/?added={item.id}")
        self.assertEqual(item.user, self.alice)
        self.assertEqual(timezone.localtime(item.due_date).date(), timezone.localdate())
        self.assertFalse(item.status)
        page = self.client.get(res["Location"])
        self.assertIn(item, page.context["today_items"])

    def test_quick_add_needs_post_and_text(self):
        self.assertEqual(self.client.get("/todolist/quickadd/").status_code, 405)
        before = Item.objects.count()
        self.client.post("/todolist/quickadd/", {"text": "   "})
        self.assertEqual(Item.objects.count(), before)

    def test_quick_add_requires_sign_in(self):
        self.client.logout()
        res = self.client.post("/todolist/quickadd/", {"text": "x"})
        self.assertTrue(res["Location"].startswith("/todolist/login/"))

    def test_more_options_carries_the_text_into_the_form(self):
        page = self.client.get("/todolist/additem/?text=Book+flights")
        self.assertEqual(page.context["form"].initial["todo_item"], "Book flights")

    def test_overdue_tasks_are_grouped_first(self):
        late = make_item(self.alice, todo_item="Pay the bill", due_date=timezone.now() - datetime.timedelta(days=2))
        page = self.client.get("/todolist/")
        self.assertIn(late, page.context["overdue_items"])
        self.assertNotIn(late, page.context["due_today_items"])
        today = page.content.decode().split('id="Today"')[1].split('id="Recurring"')[0]
        self.assertLess(today.index("Overdue"), today.index("Pay the bill"))

    def test_layout_has_one_primary_action_and_account_menu(self):
        body = self.client.get("/todolist/").content.decode()
        self.assertIn('class="quick-add"', body)
        self.assertIn('class="account"', body)
        self.assertIn('class="bottomnav"', body)
        self.assertIn('id="filter-panel" hidden', body)
        self.assertNotIn("btn-outline-danger\" href=\"/todolist/signout/", body)
        self.assertIn(">Done <span", body)


class CalmerRows(Base):
    """UI Tier 2 (#13-#16): one meta line per task, quick due dates, project cards."""

    def setUp(self):
        super().setUp()
        self.login(self.alice)

    def test_due_labels(self):
        from .templatetags.todo_extras import due_label
        now = timezone.now()
        self.assertEqual(due_label(now), "Today")
        self.assertEqual(due_label(now + datetime.timedelta(days=1)), "Tomorrow")
        self.assertEqual(due_label(now - datetime.timedelta(days=1)), "Yesterday")
        self.assertEqual(due_label(None), "")

    def test_row_shows_meta_line_not_badges(self):
        project = Project.objects.create(user=self.alice, name="Garden")
        make_item(self.alice, todo_item="Late one", due_date=timezone.now() - datetime.timedelta(days=3),
                  project=project, tags="home, Outside", itemPriority=4)
        body = self.client.get("/todolist/").content.decode()
        row = body[body.index("Late one"):]
        row = row[:row.index("</summary>")]
        self.assertIn("Overdue ·", row)
        self.assertIn("Garden", row)
        self.assertIn("#Outside", row)
        self.assertNotIn("badge", row)
        self.assertIn("task-check prio-4", body)
        self.assertIn('class="check-hit"', body)

    def test_form_folds_rare_fields_and_opens_them_on_error(self):
        page = self.client.get("/todolist/additem/").content.decode()
        self.assertIn('data-due-offset="1"', page)
        self.assertIn('<details class="more-fields">', page)
        res = self.client.post("/todolist/additem/", {**FORM, "pomodoro_estimate": "-1"})
        self.assertContains(res, '<details class="more-fields" open>')

    def test_edit_shows_and_saves_pomodoros(self):
        item = Item.objects.create(user=self.alice, todo_item="Walk", create_date=timezone.now(), due_date=timezone.now(),
                                   status=False, pomodoro_estimate=3, pomodoro_completed=0, recurring_task=True,
                                   recurrence="daily", autoCompletePomodoro=False, itemPriority=2)
        page = self.client.get(f"/todolist/editItem/{item.id}").content.decode()
        self.assertIn('<details class="more-fields" open>', page)
        self.assertIn('name="pomodoro_estimate"', page)
        self.assertNotIn("{#", page)
        self.client.post(f"/todolist/editItem/{item.id}", {**FORM, "recurrence": "daily", "pomodoro_estimate": "5",
                                                           "pomodoro_completed": "2"})
        item.refresh_from_db()
        self.assertEqual((item.pomodoro_estimate, item.pomodoro_completed), (5, 2))
        self.client.get("/todolist/")  # the task list's daily reset check must not undo it on the same day
        item.refresh_from_db()
        self.assertEqual((item.pomodoro_estimate, item.pomodoro_completed), (5, 2))

    def test_project_cards_have_menu_and_colour(self):
        p = Project.objects.create(user=self.alice, name="Garden")
        body = self.client.get("/todolist/projects/").content.decode()
        self.assertIn('class="row-menu"', body)
        self.assertIn(p.color, body)
        self.assertIn("project-name stretched", body)
        self.assertEqual(Project(pk=1).color, Project(pk=9).color)   # stable palette by id


class DesignSystem(Base):
    """UI Tier 3 (#17-#20): tokens, dark mode, desktop sidebar, empty states."""

    def css(self):
        from django.contrib.staticfiles import finders
        return open(finders.find("todolist/style.css")).read()

    def test_colours_come_from_tokens(self):
        import re
        css = self.css()
        body = css.split("/* ---------- 2. Base ---------- */", 1)[1]
        # Outside the token blocks, hex colours only appear for fixed brand surfaces (white text, the toast).
        allowed = {"#fff", "#146c43", "#212529", "#e9ecef", "#16191d", "#8ce99a"}
        stray = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", body)) - allowed
        self.assertEqual(stray, set())
        self.assertIn(':root[data-bs-theme="dark"]', css)
        self.assertNotIn("Fantasy", css)

    def test_layout_has_theme_switch_bootstrap_53_and_sidebar(self):
        from .models import Project
        Project.objects.create(user=self.alice, name="Garden")
        self.login(self.alice)
        body = self.client.get("/todolist/").content.decode()
        self.assertIn("bootstrap@5.3.3", body)
        self.assertIn('data-theme="dark"', body)
        self.assertIn('class="sidebar"', body)
        side = body[body.index('class="sidebar"'):body.index("</aside>")]
        self.assertIn("Garden", side)
        self.assertEqual(self.client.get("/todolist/").context["sidebar"]["today_count"], 0)

    def test_sidebar_lists_only_own_unarchived_projects(self):
        from .models import Project
        Project.objects.create(user=self.alice, name="Old", archived=True)
        Project.objects.create(user=self.bob, name="Bobs")
        self.login(self.alice)
        body = self.client.get("/todolist/projects/").content.decode()
        side = body[body.index('class="sidebar"'):body.index("</aside>")]
        self.assertNotIn("Old", side)
        self.assertNotIn("Bobs", side)

    def test_friendly_empty_states(self):
        self.item.delete()
        self.login(self.alice)
        self.assertContains(self.client.get("/todolist/"), "All clear for today")
        self.assertContains(self.client.get("/todolist/projects/"), "Create a project")

    def test_signed_out_pages_have_no_sidebar(self):
        body = self.client.get("/todolist/login/").content.decode()
        self.assertNotIn('class="sidebar"', body)
        self.assertIn("<main", body)


class Notifications(Base):
    """Web Push reminders: install pieces, device sign-up, and the reminder rules."""

    def setUp(self):
        super().setUp()
        import tempfile
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
        from django.test import override_settings
        from . import push
        key = ec.generate_private_key(ec.SECP256R1())
        f = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        f.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())); f.close()
        self.override = override_settings(VAPID_PRIVATE_KEY_FILE=f.name, VAPID_SUBJECT="https://example.test")
        self.override.enable()
        push._private_key.cache_clear()
        self.addCleanup(lambda: (self.override.disable(), push._private_key.cache_clear()))
        self.sent = []
        import pywebpush
        from unittest import mock
        patcher = mock.patch.object(pywebpush, "webpush", side_effect=lambda sub, data, **kw: self.sent.append((sub["endpoint"], json.loads(data))))
        patcher.start(); self.addCleanup(patcher.stop)

    def subscribe(self, user, endpoint="https://web.push.apple.com/abc", tz="Asia/Kolkata"):
        self.client.force_login(user)
        return self.client.post("/todolist/notifications/subscribe/", data=json.dumps({
            "subscription": {"endpoint": endpoint, "keys": {"p256dh": "BPk", "auth": "xyz"}},
            "device": "iPhone · Home Screen app", "timezone": tz}), content_type="application/json")

    def test_install_pieces(self):
        sw = self.client.get("/todolist/sw.js")
        self.assertEqual(sw["Content-Type"], "application/javascript; charset=utf-8")
        self.assertEqual(sw["Service-Worker-Allowed"], "/todolist/")
        self.assertIn("showNotification", sw.content.decode())
        m = self.client.get("/todolist/manifest.webmanifest").json()
        self.assertEqual((m["scope"], m["start_url"], m["display"]), ("/todolist/", "/todolist/", "standalone"))
        self.login(self.alice)
        page = self.client.get("/todolist/").content.decode()
        self.assertIn('rel="manifest"', page)
        self.assertIn("apple-touch-icon", page)

    def test_page_shows_the_public_key_and_saves_choices(self):
        from .models import NotificationSettings
        self.login(self.alice)
        page = self.client.get("/todolist/notifications/").content.decode()
        self.assertIn('data-enabled="1"', page)
        self.assertRegex(page, r'data-key="B[A-Za-z0-9_-]{80,}"')
        self.client.post("/todolist/notifications/", {"due_reminders": "on", "lead_minutes": "60", "summary_time": "07:30"})
        prefs = NotificationSettings.objects.get(user=self.alice)
        self.assertEqual((prefs.lead_minutes, prefs.daily_summary, prefs.summary_time.hour), (60, False, 7))

    def test_subscribe_validates_and_records_timezone(self):
        from .models import NotificationSettings, PushSubscription
        self.assertEqual(self.subscribe(self.alice).status_code, 200)
        self.assertEqual(NotificationSettings.objects.get(user=self.alice).timezone, "Asia/Kolkata")
        self.assertEqual(self.subscribe(self.alice, endpoint="http://insecure").status_code, 400)
        self.assertEqual(PushSubscription.objects.count(), 1)
        sub = PushSubscription.objects.get()
        self.client.force_login(self.bob)                       # someone else can't remove it
        self.client.post(f"/todolist/notifications/devices/{sub.id}/remove/")
        self.assertTrue(PushSubscription.objects.exists())

    def test_test_button_sends_to_my_devices(self):
        self.subscribe(self.alice)
        res = self.client.post("/todolist/notifications/test/")
        self.assertEqual(res.json(), {"ok": True, "sent": 1})
        self.assertEqual(self.sent[0][1]["title"], "Notifications are on 🎉")

    def test_due_reminder_is_sent_once_before_the_due_time(self):
        from . import push
        self.subscribe(self.alice)                              # default: 15 minutes before
        now = timezone.now()
        self.item.due_date = now + datetime.timedelta(minutes=10); self.item.save()
        make_item(self.alice, todo_item="Later", due_date=now + datetime.timedelta(hours=3))
        make_item(self.alice, todo_item="Done already", status=True, due_date=now + datetime.timedelta(minutes=5))
        make_item(self.bob, todo_item="Bob's", due_date=now + datetime.timedelta(minutes=5))
        self.assertEqual(push.run_once(now), 1)
        self.assertEqual(self.sent[0][1]["title"], "Water the plants")
        self.assertTrue(self.sent[0][1]["body"].startswith("Due at "))
        self.assertEqual(push.run_once(now + datetime.timedelta(minutes=1)), 0)   # not again

    def test_morning_summary_once_per_day_in_local_time(self):
        from zoneinfo import ZoneInfo
        from . import push
        from .models import NotificationSettings
        self.subscribe(self.alice, tz="Asia/Kolkata")
        NotificationSettings.objects.filter(user=self.alice).update(due_reminders=False)
        kolkata = ZoneInfo("Asia/Kolkata")
        morning = datetime.datetime(2026, 11, 27, 8, 5, tzinfo=kolkata)
        make_item(self.alice, todo_item="Pay rent", due_date=datetime.datetime(2026, 11, 26, 9, 0, tzinfo=kolkata))
        self.item.due_date = datetime.datetime(2026, 11, 27, 18, 0, tzinfo=kolkata); self.item.save()
        self.assertEqual(push.run_once(morning - datetime.timedelta(minutes=10)), 0)   # 07:55: too early
        self.assertEqual(push.run_once(morning), 1)
        self.assertEqual(self.sent[0][1]["body"], "1 task today, 1 overdue: Pay rent, Water the plants")
        self.assertEqual(push.run_once(morning + datetime.timedelta(minutes=5)), 0)    # once a day

    def test_gone_devices_are_removed(self):
        import pywebpush
        from unittest import mock
        from . import push
        from .models import PushSubscription
        self.subscribe(self.alice)
        gone = pywebpush.WebPushException("gone", response=mock.Mock(status_code=410))
        with mock.patch.object(pywebpush, "webpush", side_effect=gone):
            self.assertEqual(push.send(self.alice, "x"), 0)
        self.assertFalse(PushSubscription.objects.exists())

    def test_without_a_key_the_page_says_so(self):
        from django.test import override_settings
        from . import push
        with override_settings(VAPID_PRIVATE_KEY_FILE=""):
            push._private_key.cache_clear()
            self.login(self.alice)
            self.assertContains(self.client.get("/todolist/notifications/"), "aren't set up on the server")
            self.assertEqual(push.run_once(), 0)
        push._private_key.cache_clear()
