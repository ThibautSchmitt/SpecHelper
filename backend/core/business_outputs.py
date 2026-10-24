"""Business-facing observations and deterministic confirmed-decision presentation."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .i18n import translate

Text = Annotated[str, Field(min_length=1, max_length=4000)]


class BusinessSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: str = Field(default="", max_length=4000)
    desired: str = Field(default="", max_length=4000)
    gap: str = Field(default="", max_length=4000)
    impacts: list[Text] = Field(default_factory=list, max_length=15)
    uncertainties: list[Text] = Field(default_factory=list, max_length=15)


class BusinessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ambiguity", "contradiction", "assumption", "unknown"]
    description: Text
    business_impact: Text
    evidence: list[Text] = Field(default_factory=list, max_length=10)


class BusinessOutputError(ValueError):
    """A safe explanation when confirmed rules cannot fit the public output contract."""


def normative_rules(values, confirmed, history, decisions=()):
    """Remove exact superseded rules and include every last human-confirmed value.

    General semantic consistency still requires the agent's evidence review; this
    deterministic boundary prevents known old values replacing the confirmed ones.
    """
    current = set(confirmed)
    superseded = {row["value"] for row in history} | {
        option["behavior"]
        for row in decisions
        for option in (
            row.get("question", {}).get("options", [])
            if isinstance(row.get("question"), dict)
            else []
        )
    }
    superseded -= current
    return list(
        dict.fromkeys([*(value for value in values if value not in superseded), *confirmed])
    )


def decision_rules(decisions):
    """Keep only the last explicitly confirmed value per key, without the dialogue."""
    latest = {}
    for decision in decisions:
        latest[decision["key"]] = decision
    return [value["value"] for value in sorted(latest.values(), key=lambda row: row["sequence"])]


def summary_markdown(summary, language="en"):
    if not summary:
        return ""
    value = BusinessSummary.model_validate(summary).model_dump()
    labels = {
        "current": "Current",
        "desired": "Desired",
        "gap": "Gap",
        "impacts": "Business impacts",
        "uncertainties": "Unresolved business questions",
    }
    lines = []
    for key, label in labels.items():
        content = value[key]
        if content:
            text = (
                "\n".join("- " + item for item in content) if isinstance(content, list) else content
            )
            lines += ["### " + translate(label, language), "", text, ""]
    if not lines:
        return ""
    return "\n".join(["## " + translate("Business summary", language), "", *lines])
