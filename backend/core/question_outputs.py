"""Bounded explanation outputs and deterministic, source-aware Markdown exports."""

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import unquote
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from .agent import Question
from .analysis_evidence import ReliabilityReport
from .artifacts import StrictModel, section
from .business_outputs import BusinessSummary, summary_markdown
from .i18n import translate

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Items = Annotated[list[Text], Field(max_length=30)]
PRIVATE_PATH = re.compile(
    r"(?<![\w])/(?:session|sessions|tmp|private|data|Users|home|root|proc|etc|run|workspace)"
    r"(?:/|\b)|(?i:[A-Z]:[\\/])"
)


def _public_text(value):
    """Refuse runtime and host paths rather than leaking them into public artifacts."""
    if isinstance(value, str):
        if PRIVATE_PATH.search(unquote(value)):
            raise ValueError("Public explanations cannot contain private filesystem paths")
    elif isinstance(value, list):
        for item in value:
            _public_text(item)
    elif isinstance(value, dict):
        for item in value.values():
            _public_text(item)
    return value


def _text_size(value):
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_text_size(item) for item in value)
    if isinstance(value, dict):
        return sum(_text_size(item) for item in value.values())
    return 0


class QuestionReference(StrictModel):
    repository: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=1000)
    symbol: str = Field(default="", max_length=500)

    @field_validator("repository", "symbol")
    @classmethod
    def single_line(cls, value):
        if any(ord(char) < 32 for char in value) or "`" in value:
            raise ValueError("Source reference metadata must be plain single-line text")
        return value

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        decoded = unquote(unquote(value))
        parts = decoded.split("/")
        if (
            decoded != value
            or decoded.startswith("/")
            or "\\" in decoded
            or ":" in decoded
            or "`" in decoded
            or any(part in {"", ".", ".."} for part in parts)
            or any(ord(char) < 32 for char in decoded)
            or PurePosixPath(decoded).is_absolute()
        ):
            raise ValueError("A source path must be a normalized repository-relative path")
        return value


class QuestionAnswer(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    summary: Text
    business_explanation: str = Field(default="", max_length=12000)
    technical_explanation: str = Field(default="", max_length=16000)
    verified_facts: Items = Field(default_factory=list)
    rules: Items = Field(default_factory=list)
    steps: Items = Field(default_factory=list)
    examples: Items = Field(default_factory=list)
    dependencies: Items = Field(default_factory=list)
    flows: Items = Field(default_factory=list)
    inferences: Items = Field(default_factory=list)
    uncertainties: Items = Field(default_factory=list)
    references: list[QuestionReference] = Field(default_factory=list, max_length=50)
    confirmed_decisions: Items = Field(default_factory=list)
    business_summary: BusinessSummary | None = None
    evidence: ReliabilityReport | None = None

    @field_validator("title")
    @classmethod
    def plain_title(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("An explanation title must be nonempty single-line text")
        return value.strip()

    @model_validator(mode="after")
    def public_content(self):
        # Repository-relative filenames may legitimately contain directories named tmp/data.
        _public_text(self.model_dump(exclude={"references"}))
        if _text_size(self.model_dump()) > 60000:
            raise ValueError("The consolidated explanation exceeds its narrative budget")
        return self


class QuestionOutput(StrictModel):
    status: Literal["READY", "PARTIAL"]
    answer: QuestionAnswer
    business_summary: BusinessSummary | None = None
    questions: list[Question] = Field(default_factory=list, max_length=5)


class QuestionReport(StrictModel):
    observed_behavior: Text
    evidence: Items = Field(default_factory=list)
    verified_facts: Items = Field(default_factory=list)
    inferences: Items = Field(default_factory=list)
    uncertainties: Items = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list, max_length=8)
    business_summary: BusinessSummary | None = None

    @model_validator(mode="after")
    def unique_questions(self):
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("Duplicate question identifiers")
        if _text_size(self.model_dump()) > 30000:
            raise ValueError("The question exploration report exceeds its narrative budget")
        return self


def _references(answer, baseline):
    repositories = {item["repository"]: item for item in baseline}
    result = []
    for reference in answer.references:
        source = repositories.get(reference.repository)
        if not source or not re.fullmatch(
            r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", source.get("sha", "")
        ):
            raise ValueError("An explanation reference must belong to a frozen Git baseline")
        branch = source.get("branch", "")
        if not isinstance(branch, str) or any(ord(char) < 32 for char in branch):
            raise ValueError("Invalid frozen Git branch")
        _public_text(reference.repository)
        _public_text(branch)
        location = f"`{reference.path}`"
        if reference.symbol:
            _public_text(reference.symbol)
            location += f" · `{reference.symbol}`"
        entry = f"{reference.repository} · {location} · {branch} · `{source['sha']}`"
        if entry not in result:
            result.append(entry)
    return result


COMMON_SECTIONS = (
    ("confirmed_decisions", "Confirmed decisions"),
    ("verified_facts", "Verified facts"),
    ("inferences", "Inferences"),
    ("uncertainties", "Uncertainties and verification limits"),
)
BUSINESS_SECTIONS = (
    ("business_explanation", "Business explanation"),
    ("rules", "Business rules"),
    ("steps", "Process steps"),
    ("examples", "Examples and special cases"),
)
TECHNICAL_SECTIONS = (
    ("technical_explanation", "Technical explanation"),
    ("dependencies", "Modules and dependencies"),
    ("flows", "Processing and data flows"),
)


def _render(answer, baseline, kind, language):
    answer = QuestionAnswer.model_validate(answer)
    references = _references(answer, baseline)
    sections = {
        "business": BUSINESS_SECTIONS,
        "technical": TECHNICAL_SECTIONS,
        "mixed": BUSINESS_SECTIONS + TECHNICAL_SECTIONS,
    }
    if kind not in sections:
        raise ValueError("Unsupported documentation format")
    values = answer.model_dump()
    lines = ["# " + answer.title, "", answer.summary, ""]
    if answer.business_summary:
        lines += [summary_markdown(answer.business_summary.model_dump(), language)]
    for key, label in sections[kind] + COMMON_SECTIONS:
        if values[key]:
            lines += section(label, values[key], language)
    lines += section("Source references", references, language)
    if answer.evidence:
        from .evidence_rendering import render_evidence

        lines += [render_evidence(answer.evidence.model_dump(), language)]
    if not references:
        lines += [
            translate("No source references were verified for this explanation.", language),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def render_answer(answer, baseline, language="en"):
    """Render the same consolidated answer for display, copy, and immutable storage."""
    return _render(answer, baseline, "mixed", language)


def render_document(answer, baseline, kind, language="en"):
    """Restate the selected immutable answer without another agent execution."""
    return _render(answer, baseline, kind, language)


def render_transfer(
    question, answer, baseline, *, version, language="en", request_id=None, created_at=None
):
    """Export selected conclusions and provenance, never a conversation or source documents."""
    if not isinstance(question, str) or not question.strip() or len(question) > 50000:
        raise ValueError("The original question must be nonempty bounded text")
    _public_text(question)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("The source answer version must be a positive integer")
    provenance = [translate("Answer version: {version}", language, version=version)]
    if request_id is not None:
        provenance.insert(
            0,
            translate("Source question: {question}", language, question=str(UUID(str(request_id)))),
        )
    if created_at is not None:
        timestamp = (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else datetime.fromisoformat(str(created_at)).isoformat()
        )
        provenance.append(translate("Answer created: {date}", language, date=timestamp))
    lines = ["# " + translate("Question context", language), ""]
    lines += section("Provenance", provenance, language)
    lines += section("Original question", question, language)
    lines += section(
        "Use and verification limits",
        translate(
            "This document records an exploration, not a requested change. Recheck its conclusions "
            "against the selected environment, branches and current source SHAs before relying on "
            "them. The user must explicitly describe the desired change.",
            language,
        ),
        language,
    )
    # Reuse only whitelisted, validated answer fields; no raw dialogue or private notes are accepted.
    lines += [_render(answer, baseline, "mixed", language)]
    return "\n".join(lines).rstrip() + "\n"
