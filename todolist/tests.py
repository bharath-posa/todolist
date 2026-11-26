import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import DeleteItem, Item


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
            "pomodoro_estimate": 2, "pomodoro_completed": 0, "itemPriority": 3})
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
        self.assertIn("Priority: 4", completed)


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
