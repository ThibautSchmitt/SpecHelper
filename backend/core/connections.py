import subprocess
import sys
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from ninja.errors import HttpError

from .agent import runtime_call
from .models import AIConnection, ConnectionAttempt, GitHubConnection
from .providers import connection_for

ACTIVE = {"STARTING", "AWAITING_USER"}


def public(attempt):
    return {
        "id": str(attempt.id),
        "provider": attempt.provider,
        "status": attempt.status,
        "verification_uri": attempt.verification_uri,
        "user_code": attempt.user_code,
        "input_required": attempt.input_required,
        "message": attempt.message,
        "expires_at": attempt.expires_at,
    }


def update(attempt, state):
    for key in ("status", "verification_uri", "user_code", "input_required", "message"):
        if key in state:
            setattr(attempt, key, state[key])
    attempt.save()
    if attempt.status == "CONNECTED" and attempt.provider != "github":
        ai = connection_for(attempt.provider)
        AIConnection.objects.update_or_create(
            pk=ai.pk,
            defaults={
                "agent": attempt.provider,
                "status": "CONNECTED",
                "account": "ChatGPT" if attempt.provider == "codex" else "Claude",
                "checked_at": timezone.now(),
                "availability": "AVAILABLE",
                "retry_after": None,
            },
        )
    return public(attempt)


@transaction.atomic
def start(provider):
    if provider == "github":
        GitHubConnection.objects.get_or_create(pk=1)
        GitHubConnection.objects.select_for_update().get(pk=1)
    else:
        ai = connection_for(provider)
        AIConnection.objects.select_for_update().get(pk=ai.pk)
        if ai.availability == "BUSY" and ai.retry_after is None:
            raise HttpError(409, "This assistant is processing a request. Retry after the result.")
    existing = ConnectionAttempt.objects.filter(
        provider=provider, status__in=ACTIVE, expires_at__gt=timezone.now()
    ).first()
    if existing:
        return public(existing)
    attempt = ConnectionAttempt.objects.create(
        provider=provider, expires_at=timezone.now() + timedelta(minutes=15)
    )
    if provider == "github":

        def launch():
            subprocess.Popen(
                [
                    sys.executable,
                    str(settings.BASE_DIR / "manage.py"),
                    "connect_github",
                    str(attempt.id),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        transaction.on_commit(launch)
        return public(attempt)
    try:
        state = runtime_call("/auth/start", {"attempt_id": str(attempt.id), "provider": provider})
    except ValueError:
        state = {
            "status": "ERROR",
            "message": "The connection service is not responding. Try again shortly.",
        }
    return update(attempt, state)


def poll(attempt):
    if attempt.status not in ACTIVE:
        return public(attempt)
    if attempt.provider != "github":
        state = runtime_call("/auth/" + str(attempt.id))
        if state.get("status") not in ACTIVE:
            return update(attempt, state)
    if attempt.expires_at <= timezone.now():
        return update(
            attempt,
            {
                "status": "EXPIRED",
                "message": "The connection timed out. Try again.",
                "input_required": False,
            },
        )
    if attempt.provider != "github":
        return update(attempt, state)
    return public(attempt)


@transaction.atomic
def cancel(attempt):
    attempt = ConnectionAttempt.objects.select_for_update().get(pk=attempt.pk)
    if attempt.status not in ACTIVE:
        return public(attempt)
    if attempt.provider != "github":
        try:
            state = runtime_call("/auth/" + str(attempt.id) + "/cancel", {})
        except ValueError:
            state = {"status": "CANCELLED"}
        if state.get("status") == "CONNECTED":
            return update(attempt, state)
    return update(
        attempt,
        {"status": "CANCELLED", "message": "Connection cancelled.", "input_required": False},
    )
