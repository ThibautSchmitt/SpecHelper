import os
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from core.worker import work_once


class Command(BaseCommand):
    help = "Process persistent SpecHelper jobs"

    def handle(self, **options):
        from core.cli_maintenance import start_inventory_refresh
        start_inventory_refresh()
        if os.environ.get("WORKER_GATEWAY") == "1":
            from core.gateway import start_gateway

            start_gateway()
        self.stdout.write("SpecHelper worker ready")
        next_git_check = 0
        while True:
            close_old_connections()
            if time.monotonic() >= next_git_check:
                from core.branch_checks import schedule_due

                try:
                    schedule_due()
                except Exception:
                    self.stderr.write("Branch check scheduling unavailable; retrying shortly.")
                next_git_check = time.monotonic() + 30
            if not work_once():
                time.sleep(0.5)
