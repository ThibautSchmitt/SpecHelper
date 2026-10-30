"""Portable business clarification data, never authority to execute instructions."""

from typing import Annotated, Literal

from ninja import Schema
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Identifier = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
]


class BusinessOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Identifier
    label: str = Field(min_length=1, max_length=160)
    behavior: Text
    relevance: Text
    benefits: Text
    limitations: Text
    consequences: Text

    @field_validator("id")
    @classmethod
    def reserved_identifier(cls, value):
        if value.casefold() == "other":
            raise ValueError("Other is supplied by the application, not by an AI option")
        return value

    @field_validator("label", "behavior", "relevance", "benefits", "limitations", "consequences")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Enter nonempty text without null characters")
        return value.strip()


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=50)
    question: str = Field(min_length=1, max_length=2000)
    kind: Literal["free", "choice"] = "free"
    purpose: Literal["clarification", "business_decision"] = Field(default="clarification", description="Factual scope or observed-behavior questions are clarification. Use business_decision only for an explicit human choice of a desired business rule.")
    decision_key: str = Field(default="", max_length=100)
    options: list[BusinessOption] = Field(default_factory=list, max_length=3)
    reason: str = Field(default="", max_length=2000)
    unknowns: list[Text] = Field(default_factory=list, max_length=8)
    conflicts_with: int | None = Field(default=None, ge=1)

    @field_validator("question", "id")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Enter nonempty text without null characters")
        return value.strip()

    @field_validator("decision_key", "reason")
    @classmethod
    def bounded_text(cls, value):
        if "\x00" in value:
            raise ValueError("Null characters are not allowed")
        return value.strip()

    @model_validator(mode="after")
    def useful_alternatives(self):
        if self.kind == "choice":
            if len(self.options) < 2 or len({item.id for item in self.options}) != len(
                self.options
            ):
                raise ValueError("Offer two or three distinct business options")
        elif self.options:
            raise ValueError("A free question does not contain predefined options")
        if self.conflicts_with and not self.reason:
            raise ValueError("Explain a conflict before changing a confirmed rule")
        return self


class ChoiceIn(Schema):
    model_config = ConfigDict(extra="forbid")
    option_id: str = Field(min_length=1, max_length=100)
    text: str = Field(default="", max_length=10000)


class AnswersIn(Schema):
    model_config = ConfigDict(extra="forbid")
    answers: dict[
        Annotated[str, Field(max_length=100)], Annotated[str, Field(max_length=10000)]
    ] = Field(default_factory=dict, max_length=100)
    choices: dict[Annotated[str, Field(max_length=100)], ChoiceIn] = Field(
        default_factory=dict, max_length=100
    )
    expected_decision_revision: int | None = Field(default=None, ge=0)
    confirm_changes: bool = False


class ReviseDecisionIn(Schema):
    model_config = ConfigDict(extra="forbid")
    expected_decision_revision: int = Field(ge=0)
    option_id: str | None = Field(default=None, min_length=1, max_length=100)
    text: str = Field(default="", max_length=10000)
    confirm_change: bool = False
    expected_version: int | None = Field(default=None, ge=1)


class ValidationIn(Schema):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    expected_decision_revision: int = Field(ge=0)
