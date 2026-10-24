"""Independent source-first analysis, counter-analysis and active limit verification."""

from pydantic import Field

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
    "not the interpretation. State the environmental, temporal, conditional and population scope. "
    "A SQL result is an observation at a time within a bounded population, never a proof of universal "
    "validity. Historical inconsistent rows do not establish that today's code allows that action. "
    "No percentage confidence or numerical certification is permitted. Accuracy and complete review "
    "take priority over token savings. Broad exploration remains allowed when verification requires it."
)


class ReliableOrchestrator(ConfrontationOrchestrator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config.update(
            verifier_enabled=True, allow_confrontation=True, reliability_protocol="2.3"
        )
        self.run.orchestration["version"] = "2.3"
        self.run.orchestration["config"] = self.config
        self.run.save(update_fields=["orchestration"])

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

    def execute(self):
        requirement = self.checkpoint(
            "requirement",
            "analyst",
            "requirement",
            RequirementAssessment,
            "Understand the business request. Ask only blocking business questions; otherwise "
            "READY_TO_ANALYZE. Do not investigate code until the need is clear. ticket=null.",
            budget=35,
        )
        self.request.understanding = requirement.understanding
        self.request.save(update_fields=["understanding"])
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
        self.facts = {
            "independent_analyses": [analyst.model_dump(), counter.model_dump()],
            "claims_for_review": [claim.model_dump() for claim in claims],
        }
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
        verified = self.checkpoint(
            "verifier",
            "verifier",
            "synthesis",
            CounterexampleAssessment,
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
        unresolved = self.facts.get("focused_check", {}).get("remaining_uncertainties", [])
        if unresolved:
            report.blocking = True
            report.limitations = list(dict.fromkeys([*report.limitations, *unresolved]))
        self.run.orchestration["evidence"] = report.model_dump()
        self.run.save(update_fields=["orchestration"])
        if verified.questions:
            self.clarify(requirement.understanding, verified.questions)
            return
        self.facts = {
            "verified_report": report.model_dump(),
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
