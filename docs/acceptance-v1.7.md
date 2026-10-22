# v1.7 questions acceptance — October 22, 2026

## Functional coverage

| Criterion | Implemented behavior | Evidence |
|---|---|---|
| QST-01: navigation | Requests, Questions, Tickets and Settings; shared queue and connection indicators | `v17.spec.ts`, existing shell tests, desktop/mobile |
| QST-02: creation | Environment, free question, optional files and independent comparison | `test_v17_api.py`, `v17.spec.ts`, `v17-live.spec.ts` |
| QST-03: shared execution | Existing analysis jobs and orchestrator; only `answer.md`, no ticket or goal | `test_v17_flow.py`, Linux workflows |
| QST-04: conversation | Clarification before/during exploration releases the worker; answers and follow-ups retain useful history and produce immutable referenced answers | API/flow tests, API-backed browser scenario, Linux workflows |
| QST-05: copy | Exact canonical Markdown of the displayed version, including historical versions and references | Browser clipboard assertion, artifact/API equality test |
| QST-06: documentation | Optional business, technical and mixed Markdown, tied to source question/version/language/Git references | Output/API/browser tests; three-format Linux exports |
| QST-07: request form | Original environment preselected but editable; need blank; curated Markdown context previewed, optional and removable | API/browser tests; isolated attachment creation/removal |
| QST-08: normal request workflow | Derived request runs ordinary clarification, attachment analysis, comparison/review and ticket/goal publication | Shared flow tests and real Git/Linux workflows |
| QST-09: independence | Multiple derived requests, independent sessions, versions and immutable transferred attachments, links in both directions | API/flow/browser tests; question follow-up leaves earlier transfer unchanged |
| QST-10: stale source verification | Request instructions require source reinspection; current baseline differs from transferred baseline after a real source commit | Python and TypeScript Linux stand-ins actually reopen the changed worktree and assert the new SHA/code before producing the request result |

## Implementation boundaries

The existing `Request`, messages, attachments, runs, jobs, sessions and result
versions serve both intents. The workflow discriminator changes task instructions
and typed result schemas inside the same orchestrator. Existing role diversity,
provider fallback, read-only database capabilities and independent role contexts
remain shared. Question output validation rejects invalid paths and repositories;
referenced files must resolve inside the current worktree. A bounded format repair
can correct an invalid answer. Unresolved focused verification remains explicit and
forces `PARTIAL`, even if the final writer omits it.

Questions cannot use request ticket-publication routes. Saved question documents
organize the selected answer's analyzed fields without invoking another agent.
They invent no missing facts. Markdown is the supported export; no existing PDF
generator is available. Users can continue the question to obtain further detail.

Transfer exports use a whitelist of consolidated answer fields and provenance,
not raw agent reports, full conversations or original attachments. Configured
secrets are redacted. Invalid private path content is rejected with a bounded
error that does not echo validation input. The attachment is read on demand rather
than inlined into prompts. Source conclusions are reference material and cannot
override current source verification or agent security instructions.

## Verification

- Backend: **397 passed, one skipped** on disposable PostgreSQL 17, including business-database integration. The skip is a Linux-only host check; runtime behavior is tested in Docker.
- Focused question output/API/flow checks: **49 passed**, including safe export errors and ordinary request validation.
- Frontend production build and TypeScript pass. Ruff and migration consistency pass.
- Python and TypeScript complete Linux workflows pass with actual Git worktrees, shared orchestration, Bubblewrap, independent Codex/Claude terminal stand-ins, clarification, resumption, two answer versions, three documentation formats and independent request ticket/goal exports.
- These deterministic scenarios verify that the terminal reads changed source and a new SHA before relying on transferred context. They verify the application's contracts and isolation, not real model reasoning quality or provider speed.

- Browser: **80 desktop/mobile scenarios passed**, including 16 question scenarios covering controlled responses and an isolated actual API-backed workflow. Both English and French are exercised.
- Two additional read-only desktop/mobile checks passed against the deployed instance, verifying the Questions form, navigation, shared queue and absence of horizontal overflow or page errors.
- Publication review: 231 project-owned source files, 26 scanner findings reviewed as synthetic fixtures or translated labels, no configured connection credential present. Private specifications and runtime data remain excluded.

## Migration and deployment

A protected PostgreSQL backup was restored into a disposable database. Migration
0019 passed there and on the deployed instance. All fifteen checked historical
model fingerprints match before and after both migrations, including request
attachments, old result content and the existing queued job. Existing requests
default to the ordinary workflow. No existing version or artifact was rewritten.

All five Compose services run after the upgrade; the API health and Django system
checks pass. The worker was stopped while no job was running, then restarted after
the migration and fingerprint checks. The preexisting queued analysis was retained.
The deployed Questions page uses the production frontend build and actual API;
no synthetic answers were added to the team's instance.

## Connected-account limit

The connected ChatGPT account previously returned `QUOTA_EXHAUSTED`; a normal
analysis remains queued for available capacity. This release does not reset quota
state, remove that request or claim a completed real-provider question analysis.
Deterministic terminal stand-ins exercise the full application path without paid
provider calls. Existing source and database safety checks remain applicable;
source references do not prove semantic understanding or correctness of every claim.
