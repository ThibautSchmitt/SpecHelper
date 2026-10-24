"""Trusted page observations are separate from model-authored applicability assessments."""

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .official_sources import public_reference_url


class WebReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_id: str = Field(pattern=r"^web-[a-f0-9]{32}$")
    url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    consulted_at: str = Field(max_length=50)
    published_at: str = Field(default="", max_length=100)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text: str = Field(max_length=20000)
    truncated: bool = False
    status: Literal["checked"] = "checked"

    @field_validator("url")
    @classmethod
    def public_url(cls, value):
        return public_reference_url(value)

    @field_validator("consulted_at")
    @classmethod
    def aware_date(cls, value):
        if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("A Web observation needs a timezone-aware timestamp.")
        return value

    @model_validator(mode="after")
    def exact_text(self):
        if hashlib.sha256(self.text.encode()).hexdigest() != self.text_sha256:
            raise ValueError("The reference observation failed its integrity check.")
        return self


class WebSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["web"]
    reference_id: str = Field(pattern=r"^web-[a-f0-9]{32}$")
    excerpt: str = Field(min_length=1, max_length=2000)
    authority: str = Field(min_length=1, max_length=1000)
    effective_date: str = Field(default="", max_length=200)
    version: str = Field(default="", max_length=200)
    jurisdiction: str = Field(default="", max_length=300)
    scope: str = Field(min_length=1, max_length=1000)
    applicability: Literal["current", "historical", "unknown"] = "unknown"
    applicability_notes: str = Field(min_length=1, max_length=2000)


def actual_web_receipts(run):
    observations = []
    for raw in run.orchestration.get("web_checks", [])[:64]:
        try:
            observation = WebReceipt.model_validate(raw)
        except ValueError:
            continue
        if observation.reference_id not in {item.reference_id for item in observations}:
            observations.append(observation)
    return observations


def check_web_source(source, observations):
    receipt = next(
        (item for item in observations if item.reference_id == source.reference_id), None
    )
    if receipt is None or source.excerpt.strip() not in receipt.text:
        return False, [
            "An external reference could not be matched to an actual fetched page and excerpt."
        ]
    problems = []
    text = (receipt.text + " " + receipt.title + " " + receipt.url).casefold()
    if any(
        value and value.casefold() not in text for value in (source.effective_date, source.version)
    ):
        problems.append(
            "The stated external effective date or version is absent from the fetched page."
        )
    if source.applicability != "current" or not (source.effective_date or source.version):
        problems.append("The current applicability of this external reference remains unverified.")
    return True, problems
