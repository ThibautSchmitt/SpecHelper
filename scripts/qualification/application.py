"""Enqueue frozen corpus inputs through the normal isolated application workflow."""

import argparse
import hashlib
import os
import uuid
from pathlib import Path

from .harness import check_study, digest, read_json, relative_file, write_json


def require_isolated_database():
    from django.conf import settings

    from core.models import InstanceSettings

    database = settings.DATABASES["default"]
    if (
        os.environ.get("SPECHELPER_QUALIFICATION") != "1"
        or "qualification" not in str(database["NAME"]).lower()
        or "postgresql" not in database["ENGINE"]
    ):
        raise ValueError("Use an explicitly enabled, isolated PostgreSQL qualification database")
    instance = InstanceSettings.objects.filter(pk=1).first()
    if instance is None or not instance.name.lower().startswith("qualification"):
        raise ValueError("The isolated instance must be named Qualification before enqueueing cases")


def validate_configuration(configuration):
    from core.models import AIConnection
    from core.orchestration import family

    enabled = list(AIConnection.objects.filter(enabled=True))
    for role, expected in configuration["roles"].items():
        choices = [row for row in enabled if role in row.roles]
        if len(choices) != 1 or any((
            choices[0].agent != expected["provider"], choices[0].model != expected["model"],
            family(choices[0]) != expected["family"], expected.get("effort") is not None,
        )):
            raise ValueError("Enable exactly the frozen provider/model for each role; explicit effort overrides are unsupported")


def enqueue(study, configuration_id, environments, case_ids=None):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import transaction

    from core.models import Environment, Job, Request, RequestMessage
    from core.services import add_attachment, enqueue_analysis

    require_isolated_database()
    study = Path(study)
    manifest, protocol, _, _ = check_study(study)
    configuration = next((row for row in protocol["configurations"] if row["id"] == configuration_id), None)
    if configuration is None:
        raise ValueError("Unknown frozen configuration")
    validate_configuration(configuration)
    # Held-out cases require an explicit selection after the protocol is frozen.
    selected = set(case_ids) if case_ids else {row["id"] for row in manifest["cases"] if row["split"] == "development"}
    known = {row["id"] for row in manifest["cases"]}
    if not selected <= known:
        raise ValueError("Unknown requested corpus case")
    planned = []
    for frozen in manifest["cases"]:
        if frozen["id"] not in selected:
            continue
        root = study / "packets" / frozen["id"]
        packet = read_json(root / "packet.json")
        if packet["kind"] == "scope":
            continue
        available = packet["database"]["state"] == "available"
        environment = Environment.objects.get(pk=environments["available" if available else "absent"])
        sources = list(environment.repositories.all())
        actual = {row.repository.rsplit("/", 1)[-1]: row.sha for row in sources}
        expected = {row["id"]: row["git_sha"] for row in packet["repositories"]}
        if environment.status != "READY" or actual != expected or len(actual) != len(sources) or bool(environment.database_id) != available:
            raise ValueError("The environment must expose the exact frozen sources and database availability")
        for row in packet["attachments"]:
            if hashlib.sha256(relative_file(root, row["path"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("A frozen attachment changed")
        identifier = uuid.uuid5(uuid.NAMESPACE_URL, digest(manifest) + ":" + configuration_id + ":" + packet["case_id"])
        planned.append((identifier, packet, environment, root))
    identifiers = {str(row[0]) for row in planned}
    if Job.objects.filter(kind="analysis", status__in=["QUEUED", "RUNNING"]).exclude(target__in=identifiers).exists():
        raise ValueError("Finish other application runs before changing qualification batches")
    bindings = {}
    for identifier, packet, environment, root in planned:
        with transaction.atomic():
            request, created = Request.objects.get_or_create(pk=identifier, defaults={
                "workflow": packet["workflow"], "language": packet["language"],
                "need": packet["need"], "environment": environment,
                "environment_name_snapshot": environment.name,
                "analysis_protocol": "2.4", "confrontation": True,
            })
            if any(getattr(request, key) != packet[key] for key in ("need", "language", "workflow")) or request.environment_id != environment.pk:
                raise ValueError("An existing case binding was changed; do not overwrite it")
            if created:
                RequestMessage.objects.create(request=request, role="user", kind="need", content=request.need)
                for row in packet["attachments"]:
                    path = relative_file(root, row["path"])
                    add_attachment(request.pk, SimpleUploadedFile(path.name, path.read_bytes()))
                enqueue_analysis(request.pk, analysis_protocol="2.4")
            bindings[packet["case_id"]] = str(request.pk)
    return bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--environments", type=Path, required=True)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    bindings = enqueue(args.study, args.configuration, read_json(args.environments), args.cases)
    write_json(args.output, bindings)
    print("Enqueued or retained " + str(len(bindings)) + " bound application cases")


if __name__ == "__main__":
    main()
