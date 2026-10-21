import os
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from core.worker import work_once


class Command(BaseCommand):
    help = "Process persistent SpecHelper jobs"

    def handle(self, **options):
        if os.environ.get("WORKER_GATEWAY") == "1":
            from core.gateway import start_gateway

            start_gateway()
        self.stdout.write("SpecHelper worker ready")
        while True:
            close_old_connections()
            if not work_once():
                time.sleep(0.5)
