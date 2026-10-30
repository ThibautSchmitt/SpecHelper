"""Cached CLI inventory and explicit, serialized maintenance jobs."""

import re
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Literal

import httpx
from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from .agent import runtime_call
from .models import CLITool, InstanceSettings, Job

AGENTS = ("codex", "claude", "antigravity")
Agent = Literal["codex", "claude", "antigravity"]
KIND = "cli_update"
router = Router()
_recovery_checked = 0.0


class UpdateUncertain(Exception):
    """Keep admission closed until the recovery loop can confirm or roll back."""


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", value):
        raise ValueError("Invalid stable CLI version")
    return tuple(int(part) for part in value.split("."))


def service_call(path, payload=None, timeout=75):
    try:
        if not settings.CLI_MAINTENANCE_URL:
            raise ValueError("Maintenance is not configured")
        token = Path(settings.CLI_MAINTENANCE_TOKEN_FILE).read_text().strip()
        if not token:
            raise ValueError("Maintenance is not configured")
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            response = client.request("POST" if payload is not None else "GET", settings.CLI_MAINTENANCE_URL + path, json=payload, headers={"Authorization": "Bearer " + token})
        response.raise_for_status()
        if len(response.content) > 128 * 1024:
            raise ValueError("Invalid maintenance response")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid maintenance response")
        return data
    except (OSError, ValueError, httpx.HTTPError) as error:
        raise ValueError("CLI maintenance is unavailable. Try again later.") from error


def ensure_tools():
    for agent in AGENTS:
        CLITool.objects.get_or_create(agent=agent)


def public(tool):
    try:
        available = version_key(tool.latest_version) > version_key(tool.installed_version)
    except ValueError:
        available = False
    job = tool.update_job
    return {"agent": tool.agent, "installed_version": tool.installed_version, "latest_version": tool.latest_version,
            "checked_at": tool.checked_at, "check_error": tool.check_error, "update_available": available,
            "update_status": job.status if job else "", "update_error": job.error if job and job.status == "ERROR" else ""}


@router.get("/cli-tools")
def tools(request):
    ensure_tools()
    return {"items": [public(tool) for tool in CLITool.objects.select_related("update_job").order_by("agent")]}


@router.post("/cli-tools/{agent}/update")
@transaction.atomic
def request_update(request, agent: Agent):
    if not settings.CLI_MAINTENANCE_URL:
        raise HttpError(503, "CLI maintenance is unavailable. Try again later.")
    InstanceSettings.objects.get_or_create(pk=1)
    InstanceSettings.objects.select_for_update().get(pk=1)
    ensure_tools()
    # PostgreSQL cannot lock the nullable side of an outer join. Lock the tool
    # alone; the instance admission lock already serializes update requests.
    tool = CLITool.objects.select_for_update().get(agent=agent)
    if tool.update_job and tool.update_job.status in {"QUEUED", "RUNNING"}:
        return public(tool)
    if not public(tool)["update_available"]:
        raise HttpError(409, "No newer CLI version has been detected.")
    tool.update_job = Job.objects.create(kind=KIND, target=agent, payload={"version": tool.latest_version, "operation_id": str(uuid.uuid4())})
    tool.save(update_fields=["update_job"])
    return public(tool)


def refresh_inventory_if_due(force_installed=False):
    if not settings.CLI_MAINTENANCE_URL or Job.objects.filter(kind=KIND, status="RUNNING").exists():
        return
    ensure_tools()
    now = timezone.now()
    due = CLITool.objects.filter(agent="codex", next_check_at__lte=now).update(next_check_at=now + timedelta(hours=1))
    if not due and not force_installed:
        return
    try:
        installed = runtime_call("/cli-versions", timeout=30).get("versions", {})
        for agent in AGENTS:
            if installed.get(agent):
                version_key(installed[agent])
                CLITool.objects.filter(agent=agent).update(installed_version=installed[agent])
        if not due:
            return
        rows = service_call("/inventory").get("items", [])
        if not isinstance(rows, list) or len(rows) != len(AGENTS) or {row.get("agent") for row in rows if isinstance(row, dict)} != set(AGENTS):
            raise ValueError("Invalid CLI inventory")
        for row in rows:
            if row.get("latest_version"):
                version_key(row["latest_version"])
        for row in rows:
            agent, latest = row.get("agent"), row.get("latest_version", "")
            if agent not in AGENTS:
                raise ValueError("Invalid CLI inventory")
            changes = {"check_error": row.get("state") != "available"}
            if latest:
                version_key(latest)
                changes.update(latest_version=latest)
                if row.get("state") == "available":
                    changes["checked_at"] = now
            CLITool.objects.filter(agent=agent).update(**changes)
    except (ValueError, TypeError, AttributeError):
        CLITool.objects.update(check_error=True)
        CLITool.objects.filter(agent="codex").update(next_check_at=now + timedelta(minutes=1))


def start_inventory_refresh():
    if not settings.CLI_MAINTENANCE_URL:
        return
    def loop():
        initial = True
        while True:
            close_old_connections()
            try:
                refresh_inventory_if_due(force_installed=initial)
                initial = False
            except Exception:
                # Polling failures must not stop the analysis worker or expose response bodies.
                pass
            finally:
                close_old_connections()
            time.sleep(60)
    threading.Thread(target=loop, daemon=True, name="cli-inventory").start()


def perform_update(job):
    from .models import AIConnection, AIModelDiscovery
    from .providers import identity_for

    version_key(job.payload.get("version"))
    if job.target not in AGENTS:
        raise ValueError("Invalid CLI provider")
    probes = []
    for connection in AIConnection.objects.filter(agent=job.target, enabled=True, status="CONNECTED"):
        identity = identity_for(connection)
        if AIModelDiscovery.objects.filter(identity=identity, state="supported").exists():
            probes.append((connection, identity))
            break
    result = service_call("/install", {"agent": job.target, "version": job.payload["version"], "operation_id": job.payload["operation_id"]}, timeout=1020)
    try:
        if result.get("status") not in {"STAGED", "ACTIVE", "DONE"}:
            raise ValueError("CLI staging failed")
        if not Job.objects.filter(pk=job.pk, status="RUNNING").exists():
            raise ValueError("CLI maintenance ownership expired")
        result = service_call("/activate/" + job.payload["operation_id"], {})
        installed = runtime_call("/cli-versions", timeout=30).get("versions", {})
        if result.get("status") not in {"ACTIVE", "DONE"} or installed.get(job.target) != job.payload["version"]:
            raise ValueError("CLI version verification failed")
        from .model_catalog import refresh
        with transaction.atomic():
            InstanceSettings.objects.select_for_update().get(pk=1)
            # The row lock keeps other workers out until metadata verification commits.
            Job.objects.filter(pk=job.pk).update(status="DONE", finished_at=timezone.now())
            for connection, _ in probes:
                if refresh(connection).get("discovery", {}).get("state") != "supported":
                    raise ValueError("CLI metadata verification failed")
            service_call("/confirm/" + job.payload["operation_id"], {})
            CLITool.objects.filter(agent=job.target).update(installed_version=installed[job.target], check_error=False)
    except Exception:
        try:
            service_call("/rollback/" + job.payload["operation_id"], {})
            installed = runtime_call("/cli-versions", timeout=30).get("versions", {})
        except ValueError:
            raise UpdateUncertain() from None
        CLITool.objects.filter(agent=job.target).update(installed_version=installed.get(job.target, ""))
        raise ValueError("CLI update verification failed. The previous version was restored.") from None


def recover_updates():
    global _recovery_checked
    if time.monotonic() - _recovery_checked < 15:
        return
    _recovery_checked = time.monotonic()
    for job in Job.objects.filter(kind=KIND, status="RUNNING", started_at__lt=timezone.now() - timedelta(seconds=90)):
        try:
            operation = service_call("/operations/" + job.payload["operation_id"], timeout=5)
            if operation.get("status") == "RUNNING" and job.started_at > timezone.now() - timedelta(minutes=20):
                continue
            if operation.get("status") == "ACTIVE":
                if time.time() - operation.get("activated_at", 0) < 300:
                    continue
                service_call("/rollback/" + job.payload["operation_id"], {})
            version = runtime_call("/cli-versions", timeout=30).get("versions", {}).get(job.target, "")
            status = "DONE" if operation.get("status") == "DONE" and version == job.payload.get("version") else "ERROR"
            if version:
                CLITool.objects.filter(agent=job.target).update(installed_version=version)
        except (ValueError, KeyError):
            # An unreachable service may still be installing or activating.
            # Preserve the maintenance gate until its persisted journal is readable.
            continue
        Job.objects.filter(pk=job.pk, status="RUNNING").update(status=status, finished_at=timezone.now(), error="" if status == "DONE" else "CLI update interrupted. Check the displayed version and retry.")
