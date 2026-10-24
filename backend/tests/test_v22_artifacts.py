"""Independent checks of confirmed business rules and immutable public artifacts."""

import copy

import pytest

from core.business_outputs import BusinessSummary, decision_rules, summary_markdown
from core.models import AnalysisRun, Request
from core.question_outputs import QuestionOutput, render_document, render_transfer
from core.results import publish

pytestmark = pytest.mark.django_db

OLD_RULE = "Block termination until all ongoing benefits are closed."
NEW_RULE = "Allow termination with a visible warning about ongoing benefits."
OTHER_RULE = "Notify the case owner before completing termination."
LIVE_ONLY_RULE = "A later browser proposes a different rule that this run did not confirm."


def decision(identifier, sequence, key, value, previous_id=None):
    return {
        "id": identifier,
        "sequence": sequence,
        "key": key,
        "question": "What should happen to a termination with ongoing benefits?",
        "option_id": "b" if previous_id else "a",
        "option": None,
        "value": value,
        "previous_id": previous_id,
        "source_version": None,
        "created_at": "2026-10-24T00:00:00+00:00",
    }


def snapshot(*decisions, history=()):
    return {
        "business_decisions": {
            "revision": len(decisions) + len(history),
            "decisions": list(decisions),
            "history": list(history),
        }
    }


def request_and_run(environment, frozen, *, workflow="request", language="en"):
    request = Request.objects.create(
        environment=environment,
        environment_name_snapshot=environment.name,
        workflow=workflow,
        language=language,
        need="Clarify termination when benefits are still ongoing.",
        baseline=[{"repository": "company/backend", "branch": "main", "sha": "a" * 40}],
        status="ANALYZING",
        context_snapshot=copy.deepcopy(frozen),
    )
    run = AnalysisRun.objects.create(
        request=request, number=1, status="ANALYZING", context_snapshot=copy.deepcopy(frozen)
    )
    return request, run


def summary():
    return {
        "current": "The team closes ongoing cases before terminating the contract.",
        "desired": "The user can terminate with a visible warning.",
        "gap": "Termination must no longer require prior closure of every case.",
        "impacts": ["Case owners must see the warning."],
        "uncertainties": ["The warning wording remains to be confirmed."],
    }


def test_decision_rules_keep_only_the_last_confirmed_arbitration_in_sequence():
    first = decision(101, 1, "termination", OLD_RULE)
    second = decision(102, 2, "notification", OTHER_RULE)
    revised = decision(103, 3, "termination", NEW_RULE, previous_id=101)
    assert decision_rules([first, second, revised]) == [OTHER_RULE, NEW_RULE]


@pytest.mark.parametrize("language", ["en", "fr"])
def test_published_ticket_and_goal_retain_frozen_rules_when_writer_omits_them(
    environment, bundle, language
):
    earlier = decision(101, 1, "termination", OLD_RULE)
    chosen = decision(102, 2, "termination", NEW_RULE, previous_id=101)
    frozen = snapshot(chosen, history=[earlier])
    request, run = request_and_run(environment, frozen, language=language)
    request.context_snapshot = snapshot(decision(103, 3, "termination", LIVE_ONLY_RULE))
    request.conversation = [{"raw_discussion": "PRIVATE_DIALOGUE_SENTINEL"}]
    request.save(update_fields=["context_snapshot", "conversation"])
    output = bundle.model_copy(update={"business_summary": BusinessSummary(**summary())}, deep=True)
    version = publish(request.pk, run, output)

    assert version.decisions_snapshot == [chosen]
    assert version.business_summary == summary()
    assert NEW_RULE in version.ticket["acceptance_criteria"]
    assert NEW_RULE in version.ticket["expected_behavior"]
    files = {item.name: item.content for item in version.artifacts.all()}
    assert set(files) == {"ticket.md", "goal.md"}
    for content in files.values():
        assert NEW_RULE in content
        assert OLD_RULE not in content
        assert LIVE_ONLY_RULE not in content
        assert "PRIVATE_DIALOGUE_SENTINEL" not in content
    assert summary()["uncertainties"][0] in files["ticket.md"]
    assert "Repositories and baseline SHAs" not in files["ticket.md"]


def test_later_arbitration_creates_another_version_without_rewriting_old_artifacts(
    environment, bundle
):
    first_decision = decision(101, 1, "termination", OLD_RULE)
    request, first_run = request_and_run(environment, snapshot(first_decision))
    first = publish(request.pk, first_run, bundle)
    old_files = {item.name: item.content for item in first.artifacts.all()}
    revised = decision(102, 2, "termination", NEW_RULE, previous_id=101)
    second_run = AnalysisRun.objects.create(
        request=request,
        number=2,
        context_snapshot=snapshot(revised, history=[first_decision]),
        status="ANALYZING",
    )
    second = publish(request.pk, second_run, bundle)

    first.refresh_from_db()
    assert first.number == 1 and second.number == 2
    assert first.decisions_snapshot == [first_decision]
    assert second.decisions_snapshot == [revised]
    assert {item.name: item.content for item in first.artifacts.all()} == old_files
    assert OLD_RULE in old_files["ticket.md"]
    assert NEW_RULE not in old_files["ticket.md"]
    assert NEW_RULE in second.artifacts.get(name="ticket.md").content
    assert OLD_RULE not in second.artifacts.get(name="ticket.md").content
    with pytest.raises(ValueError, match="immutable"):
        first.save()


def test_oversized_confirmed_rules_are_not_silently_dropped_to_fit_a_ticket(environment, bundle):
    decisions = [
        decision(index, index, f"rule-{index}", (f"Business requirement {index} " * 40).strip())
        for index in range(1, 9)
    ]
    request, run = request_and_run(environment, snapshot(*decisions))
    with pytest.raises(ValueError):
        publish(request.pk, run, bundle)
    assert not request.versions.exists()


def test_known_superseded_rule_is_removed_from_normative_output_fields(environment, bundle):
    previous = decision(101, 1, "termination", OLD_RULE)
    chosen = decision(102, 2, "termination", NEW_RULE, previous_id=101)
    request, run = request_and_run(environment, snapshot(chosen, history=[previous]))
    output = bundle.model_copy(deep=True)
    output.ticket.expected_behavior = [OLD_RULE]
    output.ticket.acceptance_criteria = [OLD_RULE]
    output.goal.required_behavior = [OLD_RULE]
    output.goal.acceptance_criteria = [OLD_RULE]

    version = publish(request.pk, run, output)
    assert version.ticket["expected_behavior"] == [NEW_RULE]
    assert version.ticket["acceptance_criteria"] == [NEW_RULE]
    for artifact in version.artifacts.all():
        assert NEW_RULE in artifact.content
        assert OLD_RULE not in artifact.content


@pytest.mark.parametrize("language", ["en", "fr"])
def test_question_explanations_and_all_document_exports_retain_confirmed_decisions(
    environment, language
):
    chosen = decision(101, 1, "investigation", "Investigate warning behavior for case owners.")
    request, run = request_and_run(
        environment, snapshot(chosen), workflow="question", language=language
    )
    output = QuestionOutput.model_validate(
        {
            "status": "READY",
            "answer": {
                "title": "Termination behavior",
                "summary": "The explanation identifies the current termination constraint.",
                "business_explanation": "An ongoing benefit currently prevents termination.",
                "uncertainties": ["The future warning text has not been chosen."],
                "references": [
                    {"repository": "company/backend", "path": "contracts/termination.py"}
                ],
            },
            "business_summary": summary(),
        }
    )
    version = publish(request.pk, run, output)
    assert version.ticket == {}
    assert version.decisions_snapshot == [chosen]
    assert version.explanation["confirmed_decisions"] == [chosen["value"]]
    assert version.explanation["business_summary"] == summary()
    assert set(version.artifacts.values_list("name", flat=True)) == {"answer.md"}
    assert chosen["value"] in version.artifacts.get(name="answer.md").content
    for kind in ("business", "technical", "mixed"):
        document = render_document(version.explanation, version.baseline, kind, language)
        assert chosen["value"] in document
        assert summary()["uncertainties"][0] in document
    transfer = render_transfer(
        request.need,
        version.explanation,
        version.baseline,
        version=version.number,
        language=language,
        request_id=str(request.pk),
    )
    assert chosen["value"] in transfer


@pytest.mark.parametrize(
    ("language", "current_label", "desired_label", "gap_label", "impacts_label"),
    [
        ("en", "Current", "Desired", "Gap", "Business impacts"),
        ("fr", "Actuel", "Souhaité", "Écart", "Impacts métier"),
    ],
)
def test_summary_keeps_business_sections_distinct_and_does_not_invent_unknown_values(
    language, current_label, desired_label, gap_label, impacts_label
):
    full = summary_markdown(summary(), language)
    for label in (current_label, desired_label, gap_label, impacts_label):
        assert "### " + label in full
    incomplete = summary_markdown(
        {
            "current": "Inspected current behavior.",
            "uncertainties": ["Desired behavior is unknown."],
        },
        language,
    )
    assert "### " + current_label in incomplete
    assert "### " + desired_label not in incomplete
    assert "### " + gap_label not in incomplete
    assert "### " + impacts_label not in incomplete
    assert "Desired behavior is unknown." in incomplete
