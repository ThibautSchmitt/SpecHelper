> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v2.2 acceptance review

Review date: 2026-10-24. Scope: guided business clarification, confirmed decision
history, contradiction review, focused reanalysis and business validation across
Requests and Questions. Existing configured AI roles, shared queue, source/database
read-only access and immutable result versions remain the execution boundary.

The requirement mapping below describes implemented behavior and inspected tests.
Final command totals and publication/deployment status are recorded separately in
the validation section. Provider-response fixtures establish application behavior
for controlled responses; they do not establish general live model quality.

## Functional requirements

| ID | Requirement | Implementation and evidence |
| --- | --- | --- |
| V22-01 | Detect contradictions, unknowns and assumptions in the request, answers and inspected context | Typed business findings and clarification questions are available during initial assessment and after source exploration. `test_v22_flow.py` covers simple/standard source analysis, analyst, counter-analyst, reviewer and late-writer pauses, plus a conflict raised after a user follow-up. |
| V22-02 | Ask only for information that changes the functional result or ticket acceptance | Central clarification instructions require a blocking business consequence, useful alternatives and free questions where appropriate. Straight-through and open-question tests in `test_v22_flow.py`, `test_v22_decisions.py` and `v22-clarification.spec.ts` avoid artificial choice cards. |
| V22-03 | Keep unverified assumptions distinct from established facts | Structured findings distinguish assumptions, unknowns, ambiguities and contradictions. Qualified assumptions remain explicit in business-summary uncertainty. Flow and artifact tests verify that an unknown current behavior is not invented. |
| V22-04 | Offer no more than two or three concrete options, always with free-text Other / Clarify | `ClarificationQuestion` validates two or three distinct concrete options; Other belongs to the application. Decision API tests reject empty Other answers, invalid option identifiers and label-only submissions. Browser tests exercise keyboard selection and the mandatory Other field. |
| V22-05 | Explain each option's behavior, relevance, benefits, limits and business consequences | `BusinessOption` requires all six bounded explanatory fields. API/schema tests reject incomplete definitions; browser cards show their explanations together rather than hiding them in a technical document. |
| V22-06 | Suggestions never impose a choice or an opaque technical recommendation | Option controls start without a selected value. The schema accepts no unsupported recommendation/approval metadata. Confirmed decisions are created only by a user submission, and no provider proposal can approve its own rule. |
| V22-07 | Carry confirmed decisions forward and adapt later questions without redundancy | Run snapshots transmit the current confirmed values and changed decision keys as provider-independent structured context. Choice-B flows for both Requests and Questions retain the rule, ask only the dependent free question and resume normally. A repeated answered question receives one bounded correction attempt. |
| V22-08 | Explain conflicts before replacement; support confirming a change or reviewing the choice | An unconfirmed replacement returns `DECISION_CONFLICT` with old/new values and leaves the ledger unchanged. Only explicit confirmation appends the replacement. API, actual worker and browser tests exercise both review and confirmation. |
| V22-09 | Keep decision order, immutable history and binding to the relevant result versions | Append-only decision records retain sequence, previous record and originating result context. ResultVersion stores its own decision snapshot. API/artifact tests preserve older rules and generated files; historical browser views use selected-version data rather than the current live ledger. |
| V22-10 | Revisit decisions and queue focused reanalysis of affected conclusions | Revision checks require the current decision revision and result number. Confirmed changes queue a normal analysis with explicit changed-decision keys and targeted-reanalysis context. Source/library snapshots and previous artifacts remain unchanged; facts invalidated by a revised decision are not reused blindly. |
| V22-11 | Present Current / Desired / Gap / Business impacts where established | Structured business summaries retain only supplied observations, desired behavior, gap, impacts and explicit uncertainty. English/French artifact and browser tests keep the sections distinct and omit unknown values. No class or filename is required to understand the business summary. |
| V22-12 | Include the latest confirmed rules and acceptance criteria in the ticket, with unresolved uncertainty | Publication deterministically includes the frozen confirmed rules in expected behavior and acceptance criteria. Exact known superseded and unchosen option values are removed from normative fields. Tests verify writer omission, revision, uncertainty retention and refusal to drop oversized rules. General semantic consistency still requires evidence review and human validation. |
| V22-13 | Retain detailed decisions and technical context in goal.md without imposing technical details on the user | goal.md includes confirmed business decisions alongside its existing source baseline, implementation constraints and expected checks. Artifact tests preserve the detailed goal and immutable historical versions without copying the discussion; business-facing clarification controls remain separate. |
| V22-14 | Reuse the same mechanism for useful clarification in Questions | Shared schemas/services power both answer routes. Flow/API/browser cases cover Question clarification, while artifact tests retain decisions and summary in answer.md, business/technical/mixed documents and transferred question context. Questions still produce no ticket or goal.md. |

## Acceptance scenarios

| Scenario | Evidence |
| --- | --- |
| AC-01: Ambiguous request produces a focused, understandable clarification | Controlled actual-worker flows and browser cards show a business question before publication; inspected source analysis may also suspend for human clarification. |
| AC-02: Useful A / B / Other alternatives explain relevance and limits | Schema tests require complete options; browser tests render all explanations and the application-provided Other choice. |
| AC-03: Other requires free text and reinjects the answer | API/browser tests reject blank text, retain a valid custom business rule and include it in the next provider context. |
| AC-04: Unambiguous request creates no artificial multiple choice | The clear-request flow publishes directly with no decisions or questions. Open Request and Question cases retain free-text controls without radios. |
| AC-05: Contradiction is shown before the retained rule changes | API and browser tests inspect unchanged history after the first conflict response; an explicit confirmation appends the replacement and queues reanalysis. |
| AC-06: Choice B changes subsequent relevant questions without losing earlier decisions | `test_choice_b_other_and_dependent_question_resume_without_ai_business_approval` covers both workflows. Browser cases retain choice B, use the shared queue and show only its dependent clarification. |
| AC-07: Current, desired, gap and impacts remain distinct where established | English/French summary tests render distinct headings, retained uncertainty and no fabricated unknown fields. |
| AC-08: Ticket and goal.md use the latest confirmed arbitration without copying the discussion | Independent publication tests verify frozen latest values, exact obsolete-value removal, no dialogue copy, old-version immutability and fail-closed ticket bounds. |
| AC-09: Multi-AI configuration remains administrative | Existing request/question creation-form regressions retain automatic configured comparison and no per-request confrontation checkbox. Clarification adds no role/model policy control to the business form. |
| AC-10: Light/dark interface and shared-queue clarification/resumption work | Desktop/mobile English/French browser cases exercise appearance and queue navigation. Actual-worker tests finish the pending job, release its account lease and leave no active worker while awaiting an answer. |

## Verification sources

- `backend/tests/test_v22_decisions.py`: structured choices, free/Other answers,
  conflict confirmation, stale/duplicate browsers, immutable decision records,
  targeted revision, current-result binding, business validation/reopening,
  credentials, schema bounds and authenticated access.
- `backend/tests/test_v22_flow.py`: actual worker/orchestrator progression with
  controlled provider responses, source-discovered clarification, independent
  roles, dependent questions, conflict-before-change, targeted reanalysis,
  qualified assumptions, clear requests and bounded duplicate-question repair.
- `backend/tests/test_v22_artifacts.py`: deterministic frozen rules, immutable
  old/new results, exact superseded values, ticket-size refusal, English/French
  summaries and every Question export.
- `frontend/tests/v22-clarification.spec.ts`: English/French guided/open cards,
  keyboard/Other validation, conflict review, dependent questions, queue resumption,
  business summaries, historical views, approval and reopening.
- `frontend/tests/v22-live.spec.ts`: browser-to-API integration using the isolated
  application database and controlled fixture publication, rather than mocked
  decision endpoints. Final results are recorded below.

## Validation results

The final clean full backend regression reports **635 passed, 1 skipped**, with
the existing Starlette test-client deprecation warning. The host-only Linux skip
is covered by the actual container probe below. This includes 27 decision API
cases, 13 actual-worker progression cases and 10 independent artifact cases.
The last flow checks cover bounded duplicate-question repair, preservation of
earlier uncertainty when later findings arrive, and uncertainty retained from
reused verified facts. Ruff, TypeScript and the final production build pass.

Migration 0026 applied to a protected database copy with every original column
value preserved in **36 tables and 396 rows**. Migration drift check passes.
The fresh Linux runtime probe confirms UID/GID 10001, zero capabilities, enforced
seccomp, read-only sources, hidden credentials/other sessions and blocked arbitrary
network access, including four indirect-content carriers and audited broker denials.

Gitleaks reports no candidate secrets. Six local Semgrep rules cover **159
production files**, with no findings or parse errors. Existing operating-system
dependency conditions documented by the security acceptance review remain.

The final production-build access/library/model/assistant/business clarification
suite passes **52 desktop/mobile cases**, including English/French, keyboard
controls, conflict review, historical snapshots and business validation.

The final complete browser suite passes **176 cases** in one clean desktop/mobile
run. This includes both new browser-to-API cases, which exercise the actual decision
ledger, conflict confirmation, frozen publication, validation/reopening and exact
old-artifact preservation on isolated development data. Earlier fixture cleanup
failures were corrected by deleting only controlled test histories in dependency
order; the full suite was then rerun successfully.

All 328 publication files match the authoritative source inventory, are readable
UTF-8 and exclude private PDFs, credentials, runtime data and backups. This release
was implemented and verified locally; no v2.2 commit, remote push or shared-instance
deployment was performed.

Workflow tests using controlled provider responses prove application behavior for
those responses. The real API browser harness uses isolated application data and
controlled publication fixtures; it is not a paid model run. These checks do not
establish live subscription entitlement or general live semantic quality. Actual
provider runs, deployment and remote publication must be reported separately if
performed.

## Scope limits

Only a human can confirm a business decision or validate its result. AI suggestions
and source/attachment instructions never gain authority over central runtime
policy. No new Git, database or network permission is introduced. Stale versions,
missing expected revisions, unconfirmed conflicts and changes to validated
requests fail before replacing the retained rule.

Exact-value filtering does not prove that arbitrary paraphrases are semantically
consistent. Agents must review the evidence and confirmed rules, and the user
must review the resulting business intent. Missing or contradictory material
information requires clarification or an explicit unresolved limit rather than an
invented fact. Rules that cannot fit the concise ticket contract must be shortened
or split into another request; they are not silently removed.

This release does not add a developer-oriented code explorer, a detailed test-case
generation engine, complete environment comparison, source implementation or an
arbitrary branching workflow engine. It preserves the distinction between a
business-facing ticket and a technical coding-agent goal.

See the [business clarification guide](../guides/business-clarification.md),
[existing security acceptance review](acceptance-v1.9.md) and
[v2.1 library acceptance](acceptance-v2.1.md) for the surrounding boundaries.
