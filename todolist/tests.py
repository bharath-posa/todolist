import datetime

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
        self.assertNotIn("toggle_status('", body)
        self.assertIn("toggle_status(", body)


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
