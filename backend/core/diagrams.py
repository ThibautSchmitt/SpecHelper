"""Bounded explanatory graphs; Mermaid syntax never substitutes for evidence review."""

import re
from typing import Annotated, Literal

from ninja.errors import HttpError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_:-]{0,95}$")]
ClaimReference = Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")]
Label = Annotated[str, Field(min_length=1, max_length=160)]


class DiagramModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def safe_label(value):
    # Only generic business/component names belong in labels. No raw rows,
    # addresses, contact details, private paths or Mermaid/HTML directives.
    if not value.strip() or any(ord(char) < 32 or char in '<>{}`"\\;|' for char in value):
        raise ValueError("Diagram labels must be plain single-line text")
    if re.search(r"@|https?://|/(?:Users|home|workspace|session)/|\b\d[\d .+()-]{7,}\d\b", value, re.I):
        raise ValueError("Diagram labels cannot contain contact details or raw identifiers")
    from .environment_context import reject_credentials

    try:
        reject_credentials(value)
    except HttpError as error:
        raise ValueError("Diagram labels cannot contain configured credentials") from error
    return value


class DiagramNode(DiagramModel):
    id: Identifier
    label: Label
    kind: Literal["step", "decision", "state", "component", "table"] = "step"

    _label = field_validator("label")(safe_label)


class DiagramEdge(DiagramModel):
    id: Identifier
    source: Identifier
    target: Identifier
    label: Label
    meaning: Literal["existing", "hypothesis", "proposed"]
    claim_ids: list[ClaimReference] = Field(default_factory=list, max_length=10)

    _label = field_validator("label")(safe_label)


class DiagramProposal(DiagramModel):
    id: Identifier
    title: Label
    audience: Literal["business", "technical"]
    kind: Literal["process", "decision", "state", "sequence", "dependencies", "tables"]
    purpose: str = Field(min_length=1, max_length=1000)
    alternative_text: str = Field(min_length=1, max_length=3000)
    nodes: list[DiagramNode] = Field(min_length=3, max_length=24)
    edges: list[DiagramEdge] = Field(min_length=2, max_length=40)

    _title = field_validator("title")(safe_label)

    @field_validator("purpose", "alternative_text")
    @classmethod
    def plain_description(cls, value):
        for line in value.splitlines():
            if line.strip():
                safe_label(line)
        if not value.strip():
            raise ValueError("Describe what the diagram explains")
        return value

    @model_validator(mode="after")
    def connected_identifiers(self):
        nodes = {node.id for node in self.nodes}
        if len(nodes) != len(self.nodes) or len({edge.id for edge in self.edges}) != len(self.edges):
            raise ValueError("Diagram node and relation identifiers must be distinct")
        if any(edge.source not in nodes or edge.target not in nodes for edge in self.edges):
            raise ValueError("A diagram relation references an unknown node")
        if {name for edge in self.edges for name in (edge.source, edge.target)} != nodes:
            raise ValueError("Every diagram node must participate in a reviewed relation")
        return self


class DiagramRelationReview(DiagramModel):
    diagram_id: Identifier
    edge_id: Identifier
    verdict: Literal["supported", "rejected", "unavailable"]
    notes: str = Field(min_length=1, max_length=2000)


class ReviewedDiagram(DiagramModel):
    proposal: DiagramProposal
    reviews: list[DiagramRelationReview] = Field(min_length=2, max_length=40)
    mermaid: str = Field(min_length=1, max_length=30000)


def candidates(analyst, counter):
    """Namespace both independent proposals without leaking the first to the second."""
    values = []
    for role, output in (("analyst", analyst), ("counter", counter)):
        for proposal in output.diagrams:
            value = proposal.model_copy(deep=True)
            value.id = role + ":" + value.id[:80]
            for edge in value.edges:
                edge.claim_ids = [role + ":" + claim[:90] for claim in edge.claim_ids]
            values.append(value)
    return values


def mermaid_source(proposal, language="en"):
    """Generate a small safe Mermaid subset from reviewed structured relationships."""
    labels = {"existing": "Existant", "hypothesis": "Hypothèse", "proposed": "Évolution proposée"} if language == "fr" else {
        "existing": "Existing", "hypothesis": "Hypothesis", "proposed": "Proposed change",
    }
    ids = {node.id: f"n{index}" for index, node in enumerate(proposal.nodes)}
    if proposal.kind == "sequence":
        lines = ["sequenceDiagram"]
        lines.extend(f"    participant {ids[node.id]} as {node.label}" for node in proposal.nodes)
        lines.extend(f"    {ids[edge.source]}->>{ids[edge.target]}: {labels[edge.meaning]} — {edge.label}" for edge in proposal.edges)
    else:
        lines = ["flowchart TD"]
        for node in proposal.nodes:
            shape = ('{"', '"}') if node.kind == "decision" else ('["', '"]')
            lines.append(f"    {ids[node.id]}{shape[0]}{node.label}{shape[1]}")
        for edge in proposal.edges:
            arrow = "-.->" if edge.meaning != "existing" else "-->"
            lines.append(f'    {ids[edge.source]} {arrow}|"{labels[edge.meaning]} — {edge.label}"| {ids[edge.target]}')
    return "\n".join(lines)


def reviewed_diagrams(proposals, reviews, claims, language="en"):
    """Omit a graph rather than rendering any unreviewed or unsupported relationship."""
    by_claim = {claim.id: claim for claim in claims}
    result, omitted = [], []
    for proposal in proposals:
        matching = [review for review in reviews if review.diagram_id == proposal.id]
        by_edge = {review.edge_id: review for review in matching}
        valid = len(by_edge) == len(matching) and set(by_edge) == {edge.id for edge in proposal.edges}
        for edge in proposal.edges:
            valid = valid and edge.id in by_edge and by_edge[edge.id].verdict == "supported"
            if edge.meaning == "existing":
                valid = valid and bool(edge.claim_ids) and all(
                    name in by_claim and by_claim[name].status == "supported"
                    and any(source.kind in {"git", "sql"} for source in by_claim[name].sources)
                    for name in edge.claim_ids
                )
        if valid:
            result.append(ReviewedDiagram(proposal=proposal, reviews=matching,
                                          mermaid=mermaid_source(proposal, language)))
        else:
            omitted.append("A diagram was omitted because its relationships were not independently verified.")
    return result, list(dict.fromkeys(omitted))


def diagram_markdown(diagrams, language="en"):
    if not diagrams:
        return ""
    lines = ["## " + ("Diagrammes explicatifs" if language == "fr" else "Explanatory diagrams"), ""]
    for raw in diagrams:
        value = ReviewedDiagram.model_validate(raw)
        lines += ["### " + value.proposal.title, "", value.proposal.purpose, "",
                  value.proposal.alternative_text, "", "```mermaid", value.mermaid, "```", ""]
        for edge in value.proposal.edges:
            if edge.claim_ids:
                lines += ["- " + edge.label + ": " + ", ".join(edge.claim_ids)]
        lines.append("")
    return "\n".join(lines)
