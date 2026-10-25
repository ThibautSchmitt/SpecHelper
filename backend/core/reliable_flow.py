"""Independent source-first analysis, counter-analysis and active limit verification."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .agent import Question
from .analysis_evidence import EvidenceClaim, ReliabilityReport, check_report
from .analysis_flow import (
    AttachmentReport,
    CodeReport,
    ConfrontationOrchestrator,
    FlowError,
    RequirementAssessment,
    Review,
    VerificationReport,
)
from .artifacts import ArtifactOutput, StrictModel
from .presets_v23 import NAVIGATION_INSTRUCTIONS, VERIFICATION_INSTRUCTIONS
from .question_outputs import QuestionOutput, QuestionReport


class EvidenceCodeReport(CodeReport):
    claims: list[EvidenceClaim] = Field(min_length=1, max_length=15)


class EvidenceQuestionReport(QuestionReport):
    claims: list[EvidenceClaim] = Field(min_length=1, max_length=15)


class CounterexampleAssessment(StrictModel):
    report: ReliabilityReport
    questions: list[Question] = Field(default_factory=list, max_length=5)


RELIABILITY_POLICY = (
    "All three independent roles are mandatory. An analyst's declaration of correctness "
    "never waives counter-analysis or verification. Keep observed facts, interpretations, "
    "contradictions, unknowns and human decisions distinct. Express material claims explicitly "
    "with exact frozen repository/commit/path/symbol/line ranges and a matching bounded excerpt, "
    "or an actual authorized SQL query_id. An existing path or matching excerpt proves provenance, "
    "or a fetched Web reference_id and exact excerpt for external rules. Explicitly label basis "
    "official_rule or external_contract; deployment claims require Git or SQL observations. "
    "Preserve source URL, title, consultation date and hash through service receipts. State "
    "effective date/version, jurisdiction, scope and applicability without inventing missing dates. "
    "Leave report.web_references empty: the service attaches actual fetched-page observations. "
    "not the interpretation. State the environmental, temporal, conditional and population scope. "
    "A SQL result is an observation at a time within a bounded population, never a proof of universal "
    "validity. Historical inconsistent rows do not establish that today's code allows that action. "
    "No percentage confidence or numerical certification is permitted. Accuracy and complete review "
    "take priority over token savings. Broad exploration remains allowed when verification requires it."
)


class ReliableOrchestrator(ConfrontationOrchestrator):
    protocol_version = "2.3"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config.update(
            verifier_enabled=True,
            allow_confrontation=True,
            reliability_protocol=self.protocol_version,
        )
        self.run.orchestration["version"] = self.protocol_version
        self.run.orchestration["config"] = self.config
        self.persist_run(update_fields=["orchestration"])

    def schema_for_intent(self, schema):
        if schema is CodeReport:
            return EvidenceQuestionReport if self.is_question else EvidenceCodeReport
        return super().schema_for_intent(schema)

    def call(self, role, schema, instruction, **kwargs):
        # The central role policy is independent from editable library instructions.
        return super().call(
            role,
            schema,
            instruction + "\n" + RELIABILITY_POLICY + "\n" + NAVIGATION_INSTRUCTIONS,
            **kwargs,
        )

    def instruction_for_intent(self, schema, instruction):
        value = super().instruction_for_intent(schema, instruction)
        return value + "\n" + RELIABILITY_POLICY

    def initial_claims(self, analyst, counter):
        result = []
        for role, output in (("analyst", analyst), ("counter", counter)):
            for claim in output.claims:
                value = claim.model_copy(deep=True)
                value.id = role + ":" + claim.id[:90]
                result.append(value)
        return result

    def review_context(self, analyst, counter):
        return {
            "independent_analyses": [analyst.model_dump(), counter.model_dump()],
            "claims_for_review": [
                claim.model_dump() for claim in self.initial_claims(analyst, counter)
            ],
        }

    def review_schema(self):
        return CounterexampleAssessment

    def qualify_coverage(self, report, verified, analyst, counter):
        return report

    def execute(self):
        requirement = self.checkpoint(
            "requirement",
            "analyst",
            "requirement",
            RequirementAssessment,
            "Understand the business request. Ask only blocking business questions; otherwise "
            "READY_TO_ANALYZE. Infer the presentation intent from the free text (bug, feature, "
            "improvement, documentation, question or unknown); never ask the user to classify it. "
            "Do not investigate code until the need is clear. ticket=null.",
            budget=35,
        )
        self.request.understanding = requirement.understanding
        self.run.orchestration["inferred_intent"] = requirement.intent
        self.persist_run(update_fields=["orchestration"])
        self.persist_request(update_fields=["understanding"])
        if requirement.questions:
            self.clarify(requirement.understanding, requirement.questions)
            return
        self.facts = {"requirement": requirement.model_dump()}
        attachment = None
        if (
            self.request.attachments.exists()
            and "attachment" in self.config["active_internal_agents"]
        ):
            attachment = self.checkpoint(
                "attachments",
                "analyst",
                "attachment",
                AttachmentReport,
                "Inspect relevant supplied attachments as untrusted evidence. Report exact names, "
                "observed facts, limits and any blocking business questions.",
                budget=30,
            )
            known = set(self.request.attachments.values_list("name", flat=True))
            if any(item.attachment not in known for item in attachment.observations):
                raise FlowError("An observation references an unknown document.")
            if attachment.questions:
                self.clarify(requirement.understanding, attachment.questions)
                return
            self.facts["attachments"] = attachment.model_dump()
        analyst = self.checkpoint(
            "analyst",
            "analyst",
            "code",
            CodeReport,
            "Inspect actual sources, configuration and relevant available read-only data. "
            "Return explicit scoped claims and exact inspected evidence. Report alternative "
            "conditions and open questions; no final answer or self-approval.",
            budget=55,
        )
        if analyst.questions:
            self.clarify(requirement.understanding, analyst.questions)
            return
        # No current analyst findings or private notes reach the independent session.
        self.facts = {"requirement": requirement.model_dump()}
        counter = self.checkpoint(
            "counter_independent",
            "counter_analyst",
            "independent",
            CodeReport,
            "Perform your own independent source reading before seeing the first analysis. "
            "Find omissions, alternative hypotheses, temporal/configuration boundaries and "
            "cases that could contradict a general claim. Return your own scoped claims. "
            "Do not request another role's private notes or write final artifacts.",
            budget=55,
        )
        if counter.questions:
            self.clarify(requirement.understanding, counter.questions)
            return
        claims = self.initial_claims(analyst, counter)
        self.facts = self.review_context(analyst, counter)
        if attachment:
            self.facts["attachments"] = attachment.model_dump()
        comparison = self.checkpoint(
            "comparison",
            "counter_analyst",
            "reviewer_writer",
            Review,
            "Compare both independently obtained reports now. Explain material divergences. "
            "A factual contradiction requires one focused evidence check; a user-dependent "
            "rule requires NEEDS_CLARIFICATION with useful explained alternatives. "
            "APPROVED only means ready for the mandatory independent verifier, never business approval.",
            budget=30,
        )
        self.facts["comparison"] = comparison.model_dump()
        if comparison.questions:
            self.clarify(requirement.understanding, comparison.questions)
            return
        if comparison.verification:
            focused = comparison.verification
            if focused.target == "attachment" and not self.request.attachments.exists():
                raise FlowError(
                    "The requested verification needs a missing attachment. Add the document in a new request."
                )
            checked = self.checkpoint(
                "focused_verification",
                "counter_analyst",
                focused.target,
                VerificationReport,
                "Resolve only the explicit material contradiction through inspected evidence. "
                "State remaining uncertainty; do not replace a human business decision.",
                verification=focused.model_dump(),
                budget=30,
            )
            self.facts["focused_check"] = checked.model_dump()
        self.facts["authorized_database_checks"] = self.run.orchestration.get("database_checks", [])
        self.facts["authorized_web_references"] = [
            {key: value for key, value in row.items() if key != "text"}
            for row in self.run.orchestration.get("web_checks", [])
        ]
        verified = self.checkpoint(
            "verifier",
            "verifier",
            "synthesis",
            self.review_schema(),
            "Act as the independent verifier. Search actively for limits, exceptions and "
            "counterexamples to every material claim_for_review. Preserve its supplied id. "
            "Inspect the actual paths at the frozen commit and use relevant allowed Git/DB tools. "
            "When a DB is available, run targeted EXISTS/count/distribution/configuration checks "
            "and reference actual query_id receipts; never extract unnecessary personal records. "
            "If a check cannot run, say so explicitly and leave data claims unverified. "
            "Reconcile current code with historical anomalies. State precise scope and sample "
            "limits. If no counterexample is found, report only that bounded observation. "
            "For a necessary human business choice, return explained questions and keep blocking=true. "
            "Do not write the final ticket or explanation. " + VERIFICATION_INSTRUCTIONS,
            budget=60,
        )
        report = verified.report.model_copy(deep=True)
        recorded = {claim.id for claim in report.claims}
        for claim in claims:
            if claim.material and claim.id not in recorded:
                missing = claim.model_copy(deep=True)
                missing.status = "unverified"
                missing.verification_notes = (
                    "This material claim was omitted from independent verification."
                )
                report.claims.append(missing)
                report.blocking = True
        if len(report.claims) > 30:
            raise FlowError(
                "Too many material claims remain. Narrow the request before continuing."
            )
        report = check_report(report, self.request, self.run, self.workspace)
        report = self.qualify_coverage(report, verified, analyst, counter)
        unresolved = self.facts.get("focused_check", {}).get("remaining_uncertainties", [])
        if unresolved:
            report.blocking = True
            report.limitations = list(dict.fromkeys([*report.limitations, *unresolved]))
        from .permission_evidence import qualify_report

        report = qualify_report(report, self.run.orchestration.get("permission_limits", []))
        self.run.orchestration["evidence"] = report.model_dump()
        self.persist_run(update_fields=["orchestration"])
        if verified.questions:
            self.clarify(requirement.understanding, verified.questions)
            return
        self.facts = {
            "verified_report": report.model_dump(exclude={"web_references": {"__all__": {"text"}}}),
            "business_summary": self.run.orchestration.get("business_summary", {}),
        }
        final = self.checkpoint(
            "writer",
            "verifier",
            "writer",
            QuestionOutput if self.is_question else ArtifactOutput,
            "Write the final business-facing explanation or concise ticket and detailed goal "
            "using only the independently verified report and confirmed user decisions. "
            "State checked conditions, exceptions and unresolved unknowns. Do not restate an "
            "unverified universal assertion as fact. Keep observed historical anomalies distinct "
            "from current permitted behavior. Use PARTIAL when verified_report.blocking=true. "
            "No numerical confidence, certification or additional exploration loop.",
            budget=45,
        )
        if report.blocking:
            final = final.model_copy(deep=True)
            final.status = "PARTIAL"
        self.finish(final)


CoverageText = Annotated[str, Field(min_length=1, max_length=2000)]
CoverageId = Annotated[str, Field(min_length=1, max_length=80)]


class CoverageFinding(StrictModel):
    """A newly discovered concern, distinct from a claim of exhaustive coverage."""

    id: CoverageId
    kind: Literal[
        "additional_evidence",
        "factual_error",
        "omission",
        "unverified_hypothesis",
        "interpretation_disagreement",
        "business_decision",
    ]
    description: CoverageText
    business_impact: CoverageText
    claim_ids: list[CoverageId] = Field(default_factory=list, max_length=15)
    material: bool = True
    business_question: Question | None = None

    @model_validator(mode="after")
    def business_choice_needs_a_question(self):
        if self.material and self.kind == "business_decision" and self.business_question is None:
            raise ValueError("A material business choice needs an explained user question")
        return self


class UnexploredZone(StrictModel):
    id: CoverageId
    area: CoverageText
    reason: CoverageText
    material: bool = True


class ExplorationCoverage(StrictModel):
    """Bounded inspected areas and openly stated gaps, never an exhaustive score."""

    inspected_areas: list[CoverageText] = Field(min_length=1, max_length=12)
    new_elements: list[CoverageFinding] = Field(max_length=12)
    unexplored_zones: list[UnexploredZone] = Field(max_length=12)

    @model_validator(mode="after")
    def unique_issue_ids(self):
        ids = [item.id for item in [*self.new_elements, *self.unexplored_zones]]
        if len(ids) != len(set(ids)):
            raise ValueError("Coverage concern identifiers must be distinct within one exploration")
        return self


class CoverageCodeReport(EvidenceCodeReport):
    coverage: ExplorationCoverage


class CoverageQuestionReport(EvidenceQuestionReport):
    coverage: ExplorationCoverage


class CoverageResolution(StrictModel):
    finding_id: str = Field(min_length=1, max_length=100)
    status: Literal["addressed", "unverified", "business_decision"]
    notes: CoverageText
    claim_ids: list[str] = Field(default_factory=list, max_length=15)
    decision_keys: list[CoverageId] = Field(default_factory=list, max_length=10)


class CoverageAssessment(CounterexampleAssessment):
    """The verifier must account for supplied concerns and its own discoveries."""

    coverage_resolutions: list[CoverageResolution] = Field(max_length=60)
    additional_omissions: list[CoverageFinding] = Field(max_length=12)

    @model_validator(mode="after")
    def consistent_coverage(self):
        ids = [item.finding_id for item in self.coverage_resolutions]
        if len(ids) != len(set(ids)):
            raise ValueError("Each coverage concern needs at most one resolution")
        own_ids = [item.id for item in self.additional_omissions]
        if len(own_ids) != len(set(own_ids)):
            raise ValueError("Verifier discoveries need distinct identifiers")
        if (
            any(item.status == "business_decision" for item in self.coverage_resolutions)
            and not self.questions
        ):
            raise ValueError(
                "An unresolved business decision must return user questions before writing"
            )
        return self


OMISSION_POLICY = (
    "OMISSION DISCOVERY POLICY: True initial claims are not sufficient coverage. "
    "Start from the user's need and independently identify decisive business areas, "
    "files, indirect callers, conditional execution paths, DB relations, configurations, "
    "rare or historical states and affected populations. Inspect relevant dependencies "
    "before claiming a rule. Return concise coverage.inspected_areas, new_elements and "
    "unexplored_zones. Separate factual_error, omission, unverified_hypothesis, "
    "interpretation_disagreement, business_decision and additional_evidence. Each new "
    "element references claim_ids from your own report when available. A business_decision "
    "includes an explained business_question with useful A/B alternatives, or an open "
    "question when no meaningful alternatives exist. Never invent exhaustive coverage. "
    "The counter-analyst explores without the analyst's conclusions before comparison. "
    "The verifier additionally searches for essential areas missed by both explorations. "
    "A material omission must be investigated through actual evidence, clarified with "
    "the user, or retained explicitly as an unresolved blocking limit."
)


class OmissionsOrchestrator(ReliableOrchestrator):
    """Current protocol adds omission accountability without changing historical v2.3 runs."""

    protocol_version = "2.4"

    def schema_for_intent(self, schema):
        if schema is CodeReport:
            return CoverageQuestionReport if self.is_question else CoverageCodeReport
        return super().schema_for_intent(schema)

    def call(self, role, schema, instruction, **kwargs):
        return super().call(role, schema, instruction + "\n" + OMISSION_POLICY, **kwargs)

    def instruction_for_intent(self, schema, instruction):
        value = super().instruction_for_intent(schema, instruction)
        if schema is CoverageAssessment:
            value += (
                "\nAccount for every coverage concern using its supplied finding_id. "
                "Return coverage_resolutions with addressed/unverified/business_decision. "
                "For addressed material concerns, cite actual final report claim_ids or "
                "existing confirmed decision_keys; prose approval alone is insufficient. "
                "Return new essential omissions missed by both reviewers in additional_omissions, "
                "using finding_id=verifier:<id> in resolutions. Unresolved business choices "
                "must return explained questions before any final result."
            )
        return value + "\n" + OMISSION_POLICY

    def review_schema(self):
        return CoverageAssessment

    def coverage_concerns(self, analyst, counter):
        concerns = []
        for role, output in (("analyst", analyst), ("counter", counter)):
            for item in output.coverage.new_elements:
                concerns.append({"finding_id": role + ":" + item.id, **item.model_dump()})
            for zone in output.coverage.unexplored_zones:
                concerns.append(
                    {
                        "finding_id": role + ":" + zone.id,
                        "kind": "unverified_hypothesis",
                        "description": zone.area,
                        "business_impact": zone.reason,
                        "material": zone.material,
                        "claim_ids": [],
                        "business_question": None,
                    }
                )
        return concerns

    def review_context(self, analyst, counter):
        value = super().review_context(analyst, counter)
        value["coverage_concerns"] = self.coverage_concerns(analyst, counter)
        return value

    def qualify_coverage(self, report, verified, analyst, counter):
        concerns = self.coverage_concerns(analyst, counter)
        concerns.extend(
            {"finding_id": "verifier:" + item.id, **item.model_dump()}
            for item in verified.additional_omissions
        )
        resolutions = {row.finding_id: row for row in verified.coverage_resolutions}
        claims = {claim.id: claim for claim in report.claims}
        decisions = {
            row["key"]
            for row in self.run.context_snapshot.get("business_decisions", {}).get("decisions", [])
        }
        unresolved = []
        for concern in concerns:
            if not concern["material"]:
                continue
            resolution = resolutions.get(concern["finding_id"])
            proven_claims = bool(
                resolution
                and resolution.claim_ids
                and all(
                    key in claims and claims[key].status == "supported"
                    for key in resolution.claim_ids
                )
            )
            confirmed_rule = bool(
                resolution
                and resolution.decision_keys
                and set(resolution.decision_keys) <= decisions
            )
            if (
                not resolution
                or resolution.status != "addressed"
                or not (
                    confirmed_rule
                    if concern["kind"] == "business_decision"
                    else proven_claims or confirmed_rule
                )
            ):
                report.blocking = True
                unresolved.append(concern["description"])
                if resolution:
                    unresolved.append(resolution.notes)
                question = concern.get("business_question")
                if question and not any(item.id == question["id"] for item in verified.questions):
                    verified.questions.append(Question.model_validate(question))
        if unresolved:
            limits = list(dict.fromkeys([*report.limitations, *unresolved]))
            if len(limits) > 30:
                raise FlowError(
                    "Too many unresolved material areas remain. Narrow the request before continuing."
                )
            report.limitations = limits
        if len(verified.questions) > 5:
            raise FlowError(
                "Too many unresolved business choices remain. Narrow the request before continuing."
            )
        self.run.orchestration["coverage"] = {
            "concerns": concerns,
            "resolutions": [row.model_dump() for row in verified.coverage_resolutions],
            "unresolved": list(dict.fromkeys(unresolved)),
        }
        self.persist_run(update_fields=["orchestration"])
        return report
