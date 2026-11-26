"""Send due-task reminders and morning summaries. Runs forever, checking once a minute.

    python manage.py run_notifier          # long-running (the `notifier` container)
    python manage.py run_notifier --once   # one pass, e.g. from cron
"""
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from todolist import push


class Command(BaseCommand):
    help = "Send push reminders for due tasks and the morning summary."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
        parser.add_argument("--interval", type=int, default=60, help="Seconds between passes (default 60).")

    def handle(self, *args, once=False, interval=60, **opts):
        if not push.enabled():
            self.stderr.write("No VAPID key (DJANGO_VAPID_PRIVATE_KEY_FILE); nothing to do.")
            if once:
                return
        stop = {"now": False}
        signal.signal(signal.SIGTERM, lambda *a: stop.update(now=True))
        signal.signal(signal.SIGINT, lambda *a: stop.update(now=True))
        self.stdout.write("notifier started")
        while not stop["now"]:
            close_old_connections()
            try:
                sent = push.run_once()
                if sent:
                    self.stdout.write(f"sent {sent} notification(s)")
            except Exception as e:   # keep running; the next pass retries
                self.stderr.write(f"notifier pass failed: {e!r}")
            if once:
                break
            for _ in range(interval):
                if stop["now"]:
                    break
                time.sleep(1)
        self.stdout.write("notifier stopped")
