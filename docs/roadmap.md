# Future scope

Active guides describe the implemented v2.5 baseline and v2.7 Antigravity adapter.
v2.6 is documentary only. The summaries for v2.8 and later are future targets,
not claims that those specifications or acceptance gates are implemented.

Target-specification summaries: [v2.7](#v27---additional-ai-adapter),
[v2.8](#v28---reliability-qualification),
[v2.9](#v29---conversational-business-workflow) and
[v3.0](#v30---verified-knowledge-and-staleness).

## v2.7 - Additional AI adapter

Implemented: [Antigravity](antigravity.md) supports Google-account authorization,
optional explicit API credentials, native model discovery and the existing roles
and sandbox. One authorized native Gemini execution verified scoped source/skill
reads and structured output. Evaluation limits remain explicit; local-model
execution remains outside scope.

## v2.8 - Reliability qualification

Target: 20-30 representative anonymized Requests/Questions, independently reviewed
expected outcomes, omissions and database counterexamples, frozen model/source
contexts and a held-out evaluation portion. The three-project native observation
is smaller and failed citations; it does not satisfy that target.

## v2.9 - Conversational business workflow

Target: clearer in-thread clarification, traceable edits of the initial need and
targeted reanalysis preserving history. Existing decisions/versions remain available,
but these future interaction changes are not delivered.

## v3.0 - Verified knowledge and staleness

Target: reusable atomic facts with scoped source/blob/symbol provenance and careful
revalidation after code or configuration changes. No reusable cross-request knowledge
system or production structural index is enabled now.

## Experimental providers

Copilot is unavailable for production. Its [dated evaluation](archive/guides/copilot-evaluation.md)
retains open authentication, entitlement, quota, session, hook and network gates.
It is historical documentation review; provider documentation can change.

Consult the maintained target specification before implementation. This page introduces
no business filtering, diagrams, provider integration or execution permissions.
