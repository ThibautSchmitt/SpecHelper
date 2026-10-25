import subprocess
import sys
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from ninja.errors import HttpError

from .agent import runtime_call
from .models import AIConnection, AIIdentity, ConnectionAttempt, GitConnection, GitHubConnection
from .providers import connection_for, observe

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
        ai = (
            AIConnection.objects.filter(identity_id=attempt.identity_id).first()
            if attempt.identity_id
            else connection_for(attempt.provider)
        )
        if ai:
            observe(
                ai,
                {
                    "status": "CONNECTED",
                    "account": state.get("account")
                    or {
                        "codex": "ChatGPT",
                        "claude": "Claude",
                        "antigravity": "Antigravity",
                    }.get(attempt.provider, attempt.provider),
                    "account_key": state.get("account_key", ""),
                },
            )
    return public(attempt)


@transaction.atomic
def start(provider, identity_id=None, git_connection_id=None):
    legacy_identity = identity_id is None
    if provider == "github":
        if git_connection_id:
            GitConnection.objects.select_for_update().get(pk=git_connection_id)
        else:
            GitHubConnection.objects.get_or_create(pk=1)
            GitHubConnection.objects.select_for_update().get(pk=1)
    else:
        ai = (
            AIConnection.objects.filter(identity_id=identity_id).first()
            if identity_id
            else connection_for(provider)
        )
        if ai is None:
            raise HttpError(404, "AI connection not found")
        identity_id = ai.identity_id
        identity = AIIdentity.objects.select_for_update().get(pk=identity_id)
        AIConnection.objects.select_for_update().get(pk=ai.pk)
        if (identity.availability == "BUSY" and identity.retry_after is None) or (
            ai.availability == "BUSY" and ai.retry_after is None
        ):
            raise HttpError(409, "This assistant is processing a request. Retry after the result.")
    existing = ConnectionAttempt.objects.filter(
        provider=provider,
        git_connection_id=git_connection_id,
        status__in=ACTIVE,
        expires_at__gt=timezone.now(),
    )
    existing = (
        existing.filter(Q(identity_id=identity_id) | Q(identity_id=None))
        if legacy_identity and provider != "github"
        else existing.filter(identity_id=identity_id)
    )
    existing = existing.first()
    if existing:
        return public(existing)
    attempt = ConnectionAttempt.objects.create(
        provider=provider,
        identity_id=identity_id,
        git_connection_id=git_connection_id,
        expires_at=timezone.now() + timedelta(minutes=15),
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
        payload = {"attempt_id": str(attempt.id), "provider": provider}
        if identity.credential_id:
            payload["identity_id"] = str(identity.credential_id)
        state = runtime_call("/auth/start", payload)
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
