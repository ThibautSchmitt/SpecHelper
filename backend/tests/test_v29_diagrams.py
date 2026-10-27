"""Diagram provenance, independent relation review and safe textual exports."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from core.diagrams import (
    DiagramProposal,
    DiagramRelationReview,
    ReviewedDiagram,
    candidates,
    diagram_markdown,
    mermaid_source,
    reviewed_diagrams,
)

pytestmark = pytest.mark.django_db


def proposal(**changes):
    return DiagramProposal.model_validate({
        "id": "export", "title": "Export decision", "audience": "business", "kind": "decision",
        "purpose": "Show the archived contract exception.",
        "alternative_text": "The export checks the contract. Active contracts are included. The archived exception is a hypothesis.",
        "nodes": [{"id": "filter", "label": "Contract eligibility", "kind": "decision"},
                  {"id": "active", "label": "Active contracts"}, {"id": "archive", "label": "Archived contracts"}],
        "edges": [{"id": "active", "source": "filter", "target": "active", "label": "Eligible", "meaning": "existing", "claim_ids": ["analyst:eligibility"]},
                  {"id": "archive", "source": "filter", "target": "archive", "label": "Historical exception", "meaning": "hypothesis"}],
        **changes,
    })


def reviews(verdict="supported"):
    return [DiagramRelationReview(diagram_id="export", edge_id=edge, verdict=verdict,
                                  notes="Checked against the frozen source; exception is explicitly a hypothesis.")
            for edge in ("active", "archive")]


def claim(status="supported", kind="git"):
    return SimpleNamespace(id="analyst:eligibility", status=status, sources=[SimpleNamespace(kind=kind)])


def test_nontrivial_diagram_requires_independent_review_and_real_source_claims():
    diagrams, limits = reviewed_diagrams([proposal()], reviews(), [claim()])
    assert len(diagrams) == 1 and not limits
    source = diagrams[0].mermaid
    assert 'flowchart TD' in source and 'Existing — Eligible' in source
    assert 'Hypothesis — Historical exception' in source and '-.->' in source
    assert source == mermaid_source(proposal())
    exported = diagram_markdown([diagrams[0].model_dump()])
    assert '```mermaid\n' + source in exported
    assert 'analyst:eligibility' in exported and proposal().alternative_text in exported


@pytest.mark.parametrize("verdict,claims", [("rejected", [claim()]), ("unavailable", [claim()]),
                                           ("supported", []), ("supported", [claim("unverified")]),
                                           ("supported", [claim(kind="web")])])
def test_syntax_cannot_make_an_unsupported_existing_relation_true(verdict, claims):
    result, limits = reviewed_diagrams([proposal()], reviews(verdict), claims)
    assert not result and limits


def test_an_omitted_exception_review_or_duplicate_review_rejects_entire_graph():
    assert not reviewed_diagrams([proposal()], reviews()[:1], [claim()])[0]
    assert not reviewed_diagrams([proposal()], reviews() + reviews()[:1], [claim()])[0]


def test_independent_graphs_are_namespaced_only_after_both_reports_exist():
    value = proposal()
    value.edges[0].claim_ids = ["eligibility"]
    original = value.model_dump()
    analyst, counter = SimpleNamespace(diagrams=[value]), SimpleNamespace(diagrams=[value.model_copy(deep=True)])
    combined = candidates(analyst, counter)
    assert [item.id for item in combined] == ["analyst:export", "counter:export"]
    assert combined[0].edges[0].claim_ids == ["analyst:eligibility"]
    assert combined[1].edges[0].claim_ids == ["counter:eligibility"]
    assert value.model_dump() == original


@pytest.mark.parametrize("claim_id", ["1", "claim." + "x" * 90])
def test_qualified_claim_references_keep_numeric_and_long_valid_ids(claim_id):
    value = proposal()
    value.edges[0].claim_ids = [claim_id]
    value = DiagramProposal.model_validate(value.model_dump())
    qualified = candidates(SimpleNamespace(diagrams=[value]), SimpleNamespace(diagrams=[]))[0]
    checked_claim = SimpleNamespace(id="analyst:" + claim_id[:90], status="supported", sources=[SimpleNamespace(kind="git")])
    checks = [review.model_copy(update={"diagram_id": qualified.id}) for review in reviews()]
    result, limits = reviewed_diagrams([qualified], checks, [checked_claim])
    assert len(result) == 1 and not limits
    assert ReviewedDiagram.model_validate(result[0].model_dump()).proposal.edges[0].claim_ids == [checked_claim.id]


@pytest.mark.parametrize("label", ['Name <script>', 'user@example.com', '012345678901234', 'Step;click n1', 'Step\nparticipant raw', '```mermaid', '"Injected"]'])
def test_labels_reject_injected_syntax_contact_details_and_raw_identifiers(label):
    raw = proposal().model_dump()
    raw["nodes"][0]["label"] = label
    with pytest.raises(ValidationError):
        DiagramProposal.model_validate(raw)


def test_invalid_references_and_trivial_graphs_are_rejected():
    raw = proposal().model_dump()
    raw["edges"][0]["target"] = "missing"
    with pytest.raises(ValidationError):
        DiagramProposal.model_validate(raw)
    with pytest.raises(ValidationError):
        proposal(nodes=[{"id": "single", "label": "One fact"}], edges=[])
    assert reviewed_diagrams([], [], []) == ([], [])
    assert diagram_markdown([]) == ""


def test_sequence_and_french_export_keep_meanings_explicit():
    value = proposal(kind="sequence", audience="technical")
    value.edges[1].meaning = "proposed"
    result, _ = reviewed_diagrams([value], reviews(), [claim()], "fr")
    assert 'sequenceDiagram' in result[0].mermaid
    assert 'Évolution proposée' in result[0].mermaid and 'Existant' in result[0].mermaid
    assert 'Diagrammes explicatifs' in diagram_markdown([result[0].model_dump()], "fr")
