"""Typed public outputs. Only these curated fields reach tickets and goals."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .i18n import translate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanTicket(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    context: str = Field(min_length=1, max_length=2000)
    need: str = Field(min_length=1, max_length=1500)
    expected_behavior: list[str] = Field(min_length=1, max_length=12)
    proposed_solution: str = Field(min_length=1, max_length=2500)
    technical_impact: list[str] = Field(min_length=1, max_length=12)
    risks: list[str] = Field(max_length=8)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def concise(self):
        words = []
        for value in self.model_dump().values():
            for text in value if isinstance(value, list) else [value]:
                words.extend(text.split())
        if len(words) > 700:
            raise ValueError("The human ticket exceeds 700 words")
        return self


class DevelopmentGoal(StrictModel):
    business_intent: str = Field(min_length=1, max_length=4000)
    current_behavior: str = Field(min_length=1, max_length=6000)
    required_behavior: list[str] = Field(min_length=1, max_length=20)
    technical_context: list[str] = Field(min_length=1, max_length=25)
    relevant_files: list[str] = Field(min_length=1, max_length=25)
    constraints: list[str] = Field(max_length=20)
    implementation_guidance: list[str] = Field(min_length=1, max_length=25)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)
    tests_expected: list[str] = Field(min_length=1, max_length=20)
    useful_attachments: list[str] = Field(
        max_length=20,
        description="Exact useful attachment names, without Markdown or commentary. An empty list if none.",
    )


class ArtifactOutput(StrictModel):
    status: Literal["READY", "PARTIAL"]
    ticket: HumanTicket
    goal: DevelopmentGoal
    technical_summary: str = Field(min_length=1, max_length=4000)


HUMAN_SECTIONS = {
    "context": "Context",
    "need": "Need",
    "expected_behavior": "Expected behavior",
    "proposed_solution": "Proposed solution",
    "technical_impact": "Technical impact",
    "risks": "Considerations",
    "acceptance_criteria": "Acceptance criteria",
}
GOAL_CONSTRAINTS = [
    "Independently verify the cited sources and symbols before making changes; this document does not prove that the code has not changed.",
    "Preserve existing behavior outside the stated need and reuse project patterns.",
    "Do not refactor or clean up code unrelated to the objective.",
    "Do not change the database unless the need and acceptance criteria explicitly require it.",
]


def section(label, content, language="en"):
    text = "\n".join("- " + item for item in content) if isinstance(content, list) else content
    return [
        "## " + translate(label, language),
        "",
        text or translate("No items identified.", language),
        "",
    ]


def render_human(ticket, language="en"):
    lines = ["# " + ticket["title"], ""]
    for key, label in HUMAN_SECTIONS.items():
        lines += section(label, ticket[key], language)
    return "\n".join(lines).rstrip() + "\n"


def render_goal(goal, baseline, attachments, language="en", context_snapshot=None):
    known = {a.name: a for a in attachments}
    if set(goal["useful_attachments"]) - set(known):
        raise ValueError("The goal references an unknown attachment")

    def localized_section(label, content):
        return section(label, content, language)

    lines = ["# " + translate("Goal", language), ""]
    lines += localized_section("Business intent", goal["business_intent"])
    lines += localized_section("Current behavior", goal["current_behavior"])
    lines += localized_section("Required behavior", goal["required_behavior"])
    lines += localized_section("Technical context", goal["technical_context"])
    lines += localized_section(
        "Repositories and baseline SHAs",
        [f"{r['repository']} · {r['branch']} · `{r['sha']}`" for r in baseline],
    )
    lines += localized_section("Relevant files / symbols", goal["relevant_files"])
    lines += localized_section(
        "Constraints",
        list(
            dict.fromkeys(
                [translate(item, language) for item in GOAL_CONSTRAINTS] + goal["constraints"]
            )
        ),
    )
    lines += localized_section("Implementation guidance", goal["implementation_guidance"])
    lines += localized_section("Acceptance criteria", goal["acceptance_criteria"])
    lines += localized_section("Tests expected", goal["tests_expected"])
    lines += localized_section("Attachments", goal["useful_attachments"])
    if context_snapshot:
        references = []
        instructions = context_snapshot.get("instructions", {})
        if instructions.get("text"):
            references.append("instructions · SHA-256 `" + instructions["sha256"] + "`")
        references += [
            f"{item['name']} · {item['filename']} · v{item['version']} · SHA-256 `{item['sha256']}`"
            for item in context_snapshot.get("resources", [])
        ]
        if references:
            lines += localized_section("Frozen environment context", references)
    return "\n".join(lines).rstrip() + "\n"
