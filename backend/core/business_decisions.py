"""Human-confirmed business decisions, explicit conflicts and result approval."""

import copy
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from .clarification_schema import ClarificationQuestion, ReviseDecisionIn, ValidationIn
from .environment_context import reject_credentials
from .models import BusinessDecision, BusinessValidation, Request, RequestMessage
from .sensitive_data import configured_secrets, redact

router = Router(tags=["Business decisions"])
BUSY = {
    "QUEUED",
    "UNDERSTANDING",
    "ANALYZING",
    "REVIEWING",
    "GENERATING_RESULT",
    "CONTINUING_CONVERSATION",
    "GENERATING_TICKET",
}


class DecisionConflict(HttpError):
    def __init__(self, conflicts, revision):
        super().__init__(
            409,
            "This answer changes a confirmed decision. Confirm the change or review your choice.",
        )
        self.conflicts, self.revision = conflicts, revision


def safe_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 10000 or "\x00" in value:
        raise HttpError(422, "Enter a nonempty business answer of at most 10000 characters.")
    value = value.strip()
    reject_credentials(value)
    if redact(value, configured_secrets()) != value:
        raise HttpError(422, "Keep credentials outside business answers.")
    return value


def describe(decision):
    return {
        "id": decision.pk,
        "sequence": decision.sequence,
        "revision": decision.revision,
        "key": decision.key,
        "question": copy.deepcopy(decision.question),
        "option_id": decision.option_id,
        "option": copy.deepcopy(decision.option),
        "value": decision.value,
        "previous_id": decision.previous_id,
        "source_version": decision.source_version,
        "created_at": decision.created_at.isoformat(),
    }


def snapshot_for_request(request):
    history = [describe(row) for row in request.business_decisions.order_by("sequence")]
    active = {}
    for value in history:
        active[value["key"]] = value
    return {
        "revision": request.decision_revision,
        "decisions": sorted(active.values(), key=lambda value: value["sequence"]),
        "history": history,
    }


def active_decisions(request):
    return {value["key"]: value for value in snapshot_for_request(request)["decisions"]}


def assert_editable(request):
    if request.validated_version is not None:
        raise HttpError(409, "Reopen the validated request before changing its decisions.")


def check_revision(request, expected, required=False):
    if expected is None and not required:
        return
    if expected is None or request.decision_revision != expected:
        raise HttpError(409, "The business decisions have changed. Refresh before answering.")


def prepare_questions(request, questions):
    """Accept suggestions as data and bind conflicts to this request's actual ledger."""
    values, ids, keys = [], set(), set()
    active = active_decisions(request)
    by_id = {row["id"]: row for row in active.values()}
    for raw in questions:
        question = ClarificationQuestion.model_validate(
            raw.model_dump() if hasattr(raw, "model_dump") else raw
        )
        if question.conflicts_with is not None:
            previous = by_id.get(question.conflicts_with)
            if previous is None:
                raise ValueError("The clarification refers to an unavailable business decision.")
            question.decision_key = previous["key"]
        key = question.decision_key or question.id
        if question.id in ids or key in keys:
            raise ValueError(
                "Clarifications must have distinct question identifiers and business topics."
            )
        ids.add(question.id)
        keys.add(key)
        values.append(question.model_dump(exclude_defaults=True))
    return values


def proposed_answer(question, option_id=None, text=""):
    kind = question.get("kind", "free")
    if kind == "choice":
        if not option_id:
            raise HttpError(422, "Choose an option or describe another business rule.")
        if option_id == "other":
            value, option = safe_text(text), None
        else:
            option = next(
                (item for item in question.get("options", []) if item["id"] == option_id), None
            )
            if option is None:
                raise HttpError(422, "Choose one of the displayed business options.")
            if text.strip():
                raise HttpError(422, "Use Other to describe a different business rule.")
            value = safe_text(option["behavior"])
        return {
            "question": copy.deepcopy(question),
            "option_id": option_id,
            "option": copy.deepcopy(option),
            "value": value,
        }
    if option_id is not None:
        raise HttpError(422, "This question expects a free business answer.")
    return {
        "question": copy.deepcopy(question),
        "option_id": None,
        "option": None,
        "value": safe_text(text),
    }


def conflicts_for(request, proposals):
    active = active_decisions(request)
    conflicts = []
    for proposed in proposals:
        question = proposed["question"]
        key = question.get("decision_key") or question["id"]
        previous = active.get(key)
        if previous and previous["value"] != proposed["value"]:
            conflicts.append(
                {
                    "decision_id": previous["id"],
                    "key": key,
                    "previous": previous,
                    "proposed": proposed,
                }
            )
    return conflicts


def record_answers(request, proposals, expected_revision=None, confirm_changes=False):
    """Only an authenticated user action can append a confirmed decision revision."""
    assert_editable(request)
    check_revision(
        request,
        expected_revision,
        required=any(p["question"].get("kind") == "choice" for p in proposals),
    )
    conflicts = conflicts_for(request, proposals)
    if conflicts and expected_revision is None:
        check_revision(request, expected_revision, required=True)
    if conflicts and not confirm_changes:
        raise DecisionConflict(conflicts, request.decision_revision)
    active = active_decisions(request)
    changes = []
    latest_version = request.versions.order_by("-number").values_list("number", flat=True).first()
    sequence = request.business_decisions.aggregate(last=Max("sequence"))["last"] or 0
    for proposed in proposals:
        question = proposed["question"]
        key = question.get("decision_key") or question["id"]
        previous = active.get(key)
        if previous and previous["value"] == proposed["value"]:
            continue
        if not changes:
            request.decision_revision += 1
        sequence += 1
        BusinessDecision.objects.create(
            request=request,
            sequence=sequence,
            revision=request.decision_revision,
            key=key,
            previous_id=previous["id"] if previous else None,
            source_version=latest_version,
            **proposed,
        )
        changes.append(key)
    if changes:
        request.save(update_fields=["decision_revision", "updated_at"])
    return changes


def accept_answers(request, answers, choices=None, expected_revision=None, confirm_changes=False):
    """Keep free-text legacy submissions while requiring explicit structured choices."""
    choices = choices or {}
    if set(answers) & set(choices) or set(answers) | set(choices) != {
        q["id"] for q in request.questions
    }:
        raise HttpError(422, "Answer every question")
    questions = prepare_questions(request, request.questions)
    proposals, rendered = [], {}
    for question in questions:
        key = question["id"]
        if question.get("kind", "free") == "choice":
            if key not in choices:
                raise HttpError(422, "Choose an option or describe another business rule.")
            chosen = choices[key]
            chosen = chosen.model_dump() if hasattr(chosen, "model_dump") else chosen
            proposed = proposed_answer(question, chosen.get("option_id"), chosen.get("text", ""))
        else:
            if key not in answers:
                raise HttpError(422, "Answer every question")
            proposed = proposed_answer(question, text=answers[key])
        proposals.append(proposed)
        rendered[key] = proposed["value"]
    if request.discussion_state.get("enabled"):
        # A factual answer remains conversation context, never an inferred normative rule.
        proposals = [p for p in proposals if p["question"].get("purpose") == "business_decision"
                     and p["question"].get("kind") == "choice"]
    changed = record_answers(request, proposals, expected_revision, confirm_changes) if proposals else []
    return rendered, changed


@transaction.atomic
def revise_decision(request_id, decision_id, payload):
    request = get_object_or_404(Request.objects.select_for_update(), pk=request_id)
    # A newly requested revision follows the current review protocol; prior
    # published versions and already executing snapshots remain immutable.
    request.analysis_protocol = "2.4"
    assert_editable(request)
    check_revision(request, payload.expected_decision_revision, required=True)
    if request.status not in {"READY", "PARTIAL", "NEEDS_CLARIFICATION", "ERROR"}:
        raise HttpError(409, "Wait for the result or answer the pending questions.")
    current = next(
        (row for row in active_decisions(request).values() if row["id"] == decision_id), None
    )
    if current is None:
        raise HttpError(409, "This decision has been replaced. Refresh before editing.")
    latest = request.versions.order_by("-number").first()
    if (latest and latest.number != payload.expected_version) or (
        not latest and payload.expected_version is not None
    ):
        raise HttpError(409, "The result has changed. Refresh the page before continuing.")
    proposed = proposed_answer(current["question"], payload.option_id, payload.text)
    changed = record_answers(
        request, [proposed], payload.expected_decision_revision, payload.confirm_change
    )
    if not changed:
        return request
    request.conversation.append(
        {
            "questions": [proposed["question"]],
            "answers": {proposed["question"]["id"]: proposed["value"]},
            "decision_revision": request.decision_revision,
        }
    )
    RequestMessage.objects.create(
        request=request,
        role="user",
        kind="decision_revision",
        content=proposed["value"],
        data={"changed_decision_keys": changed, "decision_revision": request.decision_revision},
        version=latest,
    )
    request.questions = []
    from .services import queue_run, require_session_connection

    require_session_connection(request)
    return queue_run(request, continuing=True, changed_decision_keys=changed)


@transaction.atomic
def validate_result(request_id, payload, reopen=False):
    request = get_object_or_404(Request.objects.select_for_update(), pk=request_id)
    check_revision(request, payload.expected_decision_revision, required=True)
    latest = request.versions.order_by("-number").first()
    if not latest or latest.number != payload.expected_version:
        raise HttpError(409, "The result has changed. Refresh the page before continuing.")
    if request.status not in {"READY", "PARTIAL"} or request.questions:
        raise HttpError(409, "Finish the analysis and answer pending questions before validation.")
    if not reopen and latest.decisions_snapshot != snapshot_for_request(request)["decisions"]:
        raise HttpError(
            409, "The result does not reflect the current decisions. Reanalyze before validation."
        )
    if reopen:
        if request.validated_version != latest.number:
            raise HttpError(409, "This result is not awaiting reopening.")
        request.validated_version = None
    else:
        if request.validated_version is not None:
            raise HttpError(409, "This result has already been validated.")
        if request.messages.filter(kind="need_revision", created_at__gt=latest.created_at).exists():
            raise HttpError(409, "The need changed after this result. Reanalyze before validation.")
        if latest.status != "READY":
            raise HttpError(409, "Resolve blocking uncertainties before validating this request.")
        request.validated_version = latest.number
    request.save(update_fields=["validated_version", "updated_at"])
    BusinessValidation.objects.create(
        request=request,
        version=latest.number,
        decision_revision=request.decision_revision,
        action="reopened" if reopen else "validated",
    )
    return request


def workflow_request(request_id, workflow):
    return get_object_or_404(Request, pk=request_id, workflow=workflow)


def response_for(value):
    if value.workflow == "question":
        from .question_actions import question_dict

        return question_dict(value, full=True)
    from .api import request_dict

    return request_dict(value, full=True)


@router.post("/requests/{request_id}/decisions/{decision_id}/revise")
def revise_request(request, request_id: UUID, decision_id: int, payload: ReviseDecisionIn):
    workflow_request(request_id, "request")
    return response_for(revise_decision(request_id, decision_id, payload))


@router.post("/questions/{request_id}/decisions/{decision_id}/revise")
def revise_question(request, request_id: UUID, decision_id: int, payload: ReviseDecisionIn):
    workflow_request(request_id, "question")
    return response_for(revise_decision(request_id, decision_id, payload))


@router.post("/requests/{request_id}/validation")
def approve_request(request, request_id: UUID, payload: ValidationIn):
    workflow_request(request_id, "request")
    return response_for(validate_result(request_id, payload))


@router.delete("/requests/{request_id}/validation")
def reopen_request(request, request_id: UUID, payload: ValidationIn):
    workflow_request(request_id, "request")
    return response_for(validate_result(request_id, payload, reopen=True))


@router.post("/questions/{request_id}/validation")
def approve_question(request, request_id: UUID, payload: ValidationIn):
    workflow_request(request_id, "question")
    return response_for(validate_result(request_id, payload))


@router.delete("/questions/{request_id}/validation")
def reopen_question(request, request_id: UUID, payload: ValidationIn):
    workflow_request(request_id, "question")
    return response_for(validate_result(request_id, payload, reopen=True))
