import subprocess
import time

import httpx
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction

from core.login import TerminalLogin
from core.models import ConnectionAttempt, GitHubConnection
from core.secrets import encrypt


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("attempt_id")

    def handle(self, attempt_id, **options):
        def update(state):
            close_old_connections()
            ConnectionAttempt.objects.filter(pk=attempt_id).exclude(status="CANCELLED").update(
                **{
                    key: value
                    for key, value in state.items()
                    if key
                    in {"status", "verification_uri", "user_code", "input_required", "message"}
                }
            )

        def complete(home, env):
            close_old_connections()
            if ConnectionAttempt.objects.get(pk=attempt_id).status == "CANCELLED":
                raise ValueError("Connection cancelled")
            token = subprocess.check_output(
                ["gh", "auth", "token", "--hostname", "github.com"], env=env, text=True, timeout=10
            ).strip()
            with httpx.Client(timeout=15) as client:
                response = client.get(
                    "https://api.github.com/user", headers={"Authorization": "Bearer " + token}
                )
            if response.status_code != 200:
                raise ValueError("Connection refused")
            account = response.json()["login"]
            with transaction.atomic():
                attempt = ConnectionAttempt.objects.select_for_update().get(pk=attempt_id)
                if attempt.status == "CANCELLED":
                    raise ValueError("Connection cancelled")
                GitHubConnection.objects.update_or_create(
                    pk=1,
                    defaults={"secret": encrypt(token), "account": account, "status": "CONNECTED"},
                )
                ConnectionAttempt.objects.filter(pk=attempt_id).update(
                    status="CONNECTED", message="Connection successful."
                )
            return {"account": account}

        login = TerminalLogin("github", complete, update)
        login.start()
        while login.public()["status"] in {"STARTING", "AWAITING_USER"}:
            close_old_connections()
            if ConnectionAttempt.objects.get(pk=attempt_id).status == "CANCELLED":
                login.cancel()
            time.sleep(0.25)
