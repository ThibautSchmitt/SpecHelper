"""Opt-in provider qualification of already reviewed publication drafts.

No inference, credential input, draft generation, revision of pre-existing ticket
contents or external deletion. Selected uploads may add native attachment links.
Lost responses are injected after the real provider accepts a creation; subsequent
calls use the existing read-only reconciliation engine. A local write fence blocks
and reports any attempted second creation for a case, protecting test destinations.
"""

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

CONFIRMATION = "QUALIFY SPECHELPER PUBLICATIONS"
PLATFORMS = {"github", "gitlab", "jira", "glpi"}


def load_plan(path):
    plan = json.load(sys.stdin) if str(path) == "-" else json.loads(path.read_text())
    if plan.get("schema_version") != 1 or plan.get("confirmation") != CONFIRMATION:
        raise ValueError("Review the exact test drafts and supply the explicit plan confirmation")
    cases = plan.get("cases", [])
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10:
        raise ValueError("Use one to ten explicitly reviewed cases")
    keys, drafts = set(), set()
    for case in cases:
        key = str(uuid.UUID(case["idempotency_key"]))
        draft = str(uuid.UUID(case["draft_id"]))
        if key in keys or draft in drafts:
            raise ValueError("Each case needs its own stable operation key and publication draft")
        keys.add(key)
        drafts.add(draft)
        case["idempotency_key"], case["draft_id"] = key, draft
        if case.get("platform") not in PLATFORMS:
            raise ValueError("Unsupported publication platform")
        if case.get("scenario") not in {"double_confirmation", "lost_response"}:
            raise ValueError("Choose double_confirmation or lost_response")
        if not isinstance(case.get("revision"), int) or isinstance(case["revision"], bool) or case["revision"] < 1:
            raise ValueError("Supply the exact reviewed draft revision")
        if not isinstance(case.get("acknowledge_unverified"), bool):
            raise ValueError("Explicitly record the independent-verification acknowledgement")
        if not isinstance(case.get("title"), str) or not case["title"].strip():
            raise ValueError("Supply the reviewed title")
        if len(case.get("body_sha256", "")) != 64:
            raise ValueError("Supply the reviewed description digest")
        if not isinstance(case.get("attachment_sha256"), list):
            raise ValueError("Explicitly list selected attachment digests, including an empty list")
    return plan


def reviewed_payload(case):
    from core.models import TicketPublicationDraft
    from core.ticket_api import PublicationIn

    draft = TicketPublicationDraft.objects.select_related("connector", "conversation_ticket").get(pk=case["draft_id"])
    if draft.conversation_ticket_id is None:
        raise ValueError("Prepare a conversation ticket before running qualification")
    if draft.revision != case["revision"] or draft.connector.platform != case["platform"]:
        raise ValueError("The reviewed destination or draft revision changed")
    if draft.content.get("title") != case["title"]:
        raise ValueError("The reviewed title changed")
    digest = hashlib.sha256(draft.content.get("body", "").encode()).hexdigest()
    if digest != case["body_sha256"]:
        raise ValueError("The reviewed description changed")
    attachments = draft.content.get("selected_attachments", [])
    if sorted(row["sha256"] for row in attachments) != sorted(case["attachment_sha256"]):
        raise ValueError("The reviewed attachment selection changed")
    if case["platform"] == "github" and attachments:
        raise ValueError("The supported GitHub issue API cannot upload these attachments")
    values = {k: v for k, v in {**draft.content, **draft.presentation}.items() if k in PublicationIn.model_fields}
    values.update(connector_id=draft.connector_id, project=draft.project,
                  conversation_ticket_id=str(draft.conversation_ticket_id), draft_id=str(draft.pk),
                  draft_revision=draft.revision, idempotency_key=case["idempotency_key"],
                  confirmed=True, unverified_confirmed=case["acknowledge_unverified"])
    payload = PublicationIn.model_validate(values).model_dump(mode="json")
    return draft, payload


def run(plan, report_path, workers):
    from django.db import close_old_connections

    from core.models import PublishedTicket, RequestMessage
    from core.ticket_preparation import publication_source
    from core.ticket_providers import NetworkUncertain, provider_for
    from core.ticket_publication import publish, stored_publication_url

    lock = threading.RLock()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "kind": "opt-in-real-publications",
              "limits": ["No revision of pre-existing ticket contents or external deletion",
                         "Selected uploads may add provider-native attachment links",
                         "A second attempted create is blocked and fails the case",
                         "Lost-response injection occurs after provider acceptance, not inside the network"], "cases": []}

    def persist():
        with lock:
            if report_path is None:
                return
            with os.fdopen(os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as output:
                output.write(json.dumps(report, indent=2) + "\n")

    prepared = []
    guards = {}
    for case in plan["cases"]:
        draft, payload = reviewed_payload(case)
        version = publication_source(draft.conversation_ticket.request_id, ticket_id=draft.conversation_ticket_id)
        existing = PublishedTicket.objects.filter(idempotency_key=case["idempotency_key"]).first()
        previous = PublishedTicket.objects.filter(conversation_ticket=draft.conversation_ticket,
                                                  connector=draft.connector, project=draft.project).exclude(status="ERROR").first()
        if previous and str(previous.idempotency_key) != case["idempotency_key"]:
            raise ValueError("This destination has an existing operation; use its original operation key")
        row = {"draft_id": str(draft.pk), "scenario": case["scenario"], "platform": case["platform"],
               "connector_id": draft.connector_id, "request_id": str(version.request_id),
               "idempotency_key": case["idempotency_key"], "resumed_operation": bool(existing),
               "create_budget": 0 if existing and existing.status != "ERROR" else 1,
               "create_attempts": 0, "response_loss_injected": False, "observations": []}
        report["cases"].append(row)
        reference = (draft.connector_id, draft.project, draft.content["title"])
        if reference in guards:
            raise ValueError("Use distinct reviewed titles for cases sharing one destination")
        guards[reference] = row
        prepared.append((draft, payload, version, row))
    persist()

    def guarded_create(original):
        def create(provider, project, payload, reference):
            key = (provider.connector.pk, project, payload["title"])
            with lock:
                if key not in guards:
                    raise NetworkUncertain("Qualification refused an unplanned write")
                row = guards[key]
                row["create_attempts"] += 1
                persist()
                if row["create_attempts"] > row["create_budget"]:
                    raise NetworkUncertain("Qualification blocked an attempted duplicate creation")
            result = original(provider, project, payload, reference)
            if row["scenario"] == "lost_response":
                with lock:
                    row["response_loss_injected"] = True
                    persist()
                raise NetworkUncertain("Qualification dropped the accepted creation response")
            return result
        return create

    def execute(prepared_case):
        draft, payload, version, row = prepared_case

        def confirm():
            close_old_connections()
            try:
                # Fresh objects per thread; all writes use the production engine.
                current, current_payload = reviewed_payload(next(c for c in plan["cases"] if c["draft_id"] == str(draft.pk)))
                source = publication_source(version.request_id, ticket_id=current.conversation_ticket_id)
                return publish(source, current.connector, current_payload)
            finally:
                close_old_connections()

        try:
            start = time.perf_counter()
            if row["scenario"] == "double_confirmation" and not row["resumed_operation"]:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(lambda _: confirm(), range(2)))
                if len({record.pk for record in responses}) != 1:
                    raise ValueError("Concurrent confirmations returned different publications")
                record = responses[0]
                record.refresh_from_db()
            else:
                record = confirm()
            row["observations"].append(record.status)
            # UNCERTAIN only reconciles the existing operation. Never use another key.
            for _ in range(10):
                if record.status != "UNCERTAIN":
                    break
                time.sleep(2)
                record = confirm()
                row["observations"].append(record.status)
            if record.status != "PUBLISHED" or not stored_publication_url(record):
                raise ValueError("Publication remains unconfirmed; inspect it before any manual action")
            again = confirm()
            if again.pk != record.pk or row["create_attempts"] > row["create_budget"]:
                raise ValueError("Repeated confirmation did not preserve the original operation")
            count = PublishedTicket.objects.filter(conversation_ticket=draft.conversation_ticket,
                                                    destination=record.destination).count()
            events = RequestMessage.objects.filter(request_id=version.request_id, kind="ticket_publication",
                                                  data__publication_id=str(record.pk)).count()
            if count != 1 or events != 1:
                raise ValueError("Publication or conversation event is not unique")
            draft.conversation_ticket.refresh_from_db()
            if draft.conversation_ticket.active:
                raise ValueError("The confirmed publication did not release its active draft")
            if record.connector_id != draft.connector_id or record.project != draft.project:
                raise ValueError("The selected connection or destination was not preserved")
            if any(item["status"] != "TRANSFERRED" for item in record.attachment_delivery):
                raise ValueError("An attachment transfer remains uncertain; no retry was attempted")
            if len(record.attachment_delivery) != len(payload.get("attachment_ids", [])) + int(payload.get("include_goal", False)) + int(payload.get("include_diagrams", False)) + len(payload.get("document_generations", {})):
                raise ValueError("Attachment delivery does not match the explicit selection")
            row.update(status="PASS", publication_id=str(record.pk), external_id=record.external_id,
                       external_key=record.external_key, url=stored_publication_url(record),
                       seconds=time.perf_counter() - start, transferred=len(record.attachment_delivery),
                       conversation_events=events, active_draft_released=True)
        except Exception as error:
            # Provider messages can contain private URLs; retain a content-free category.
            row.update(status="FAIL", error_type=type(error).__name__)
        finally:
            persist()
            close_old_connections()

    with ExitStack() as stack:
        classes = {type(provider_for(draft.connector)) for draft, *_ in prepared}
        for provider_class in classes:
            stack.enter_context(patch.object(provider_class, "create", guarded_create(provider_class.create)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(execute, prepared))
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    persist()
    if report_path is None:
        print(json.dumps(report, indent=2))
    return all(row.get("status") == "PASS" for row in report["cases"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--confirm-test-publications", action="store_true")
    args = parser.parse_args()
    if not args.confirm_test_publications or not 1 <= args.workers <= 10:
        parser.error("Use an approved test destination, --confirm-test-publications and 1–10 workers")
    report_path = None if str(args.report) == "-" else args.report
    if report_path is not None and (args.plan.resolve() == report_path.resolve() or report_path.exists()):
        parser.error("Keep the input plan and existing reports intact; choose a new report path")
    plan = load_plan(args.plan)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    return 0 if run(plan, report_path, args.workers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
