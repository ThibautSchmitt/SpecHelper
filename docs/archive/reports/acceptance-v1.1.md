> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

> Public version: session/request identifiers and instance references are anonymized. Original evidence remains local.

# v1.1 implementation audit

This report covers v1.1 implementation and validation on October 20, 2026. Previous evidence remains in `acceptance.md`.

| Area | Implementation and evidence |
|---|---|
| Product and deployment | Business application, trusted team, five Compose services, one primary assistant, no application accounts or multi-tenancy. Only local port 3000 exposed. |
| Guided administration | Guided GitHub/ChatGPT/Claude connections, environments, identity with short label, job log. User connections preserved after migration. |
| Environment editing | Edit name/projects/versions/database with preview/confirmation; delete with typed name and revision guard. API and desktop/mobile checks. |
| Git storage and history | Shared mirror, fixed project/environment path, targeted fetch after edit, worktree verification. Legacy layouts cleaned at next sync. Real Git tests preserve historical requests after rename, version change and deletion. |
| Requests and attachments | Need, environment and attachments; no tokens/commands requested. File references in prompts, read-only access, executable formats rejected. |
| Discussion and result versions | Persistent messages, same-session continuation after results/clarification. Immutable selectable ticket/goal versions. API/browser and real ChatGPT session. |
| Ticket and goal content | Human ticket capped at 700 words; separate goal with context, exact SHAs, constraints, guidance, criteria, expected tests and independent source verification. Structured public fields, no exported chain of thought. |
| Internal profiles and skills | Five persisted profiles: Requirement Analyst, Code Analyst, Attachment Analyst, Reviewer, Ticket / Goal Writer. Seven skills including PostgreSQL and Tryton/Coog. Internal catalog; agents cannot edit it. |
| Bounded orchestration | Typed messages, dynamic pipeline, at most one targeted Code or Attachment verification. Maximum seven invocations including format repair. Tests cover both targets, simple path, resumption and invalid output. |
| Read-only execution | Minimal-change/pattern-reuse instructions; read-only Linux mounts, no push capability, filtered SQL/limited role. Actual runtime and database smokes. |
| Progress and time limits | Fast acknowledgment, progress, global 295 s limit, 285 s orchestration and per-call remaining budgets. Explicit errors, atomic publication and preserved previous result on failure. Actual timings below. |
| Data and compatibility | Stack retained; migrations for six new models; new states and compatible historical data. Django/PostgreSQL suite and migration checks. |
| Security boundaries | Network/volume separation, credentials outside prompts, no agent access to workflow. Actual read-only source/cache/files and PostgreSQL rights checked on Linux. |
| Acceptance and architecture | Thirteen criteria mapped below; orchestration in the existing worker, no additional agent microservices. |

## Acceptance criteria

| Criterion | Evidence |
|---|---|
| 1. Edit environment | `test_v11_environments.py`, `test_git.py`, `environments.spec.ts`: name, sources/versions, database, diff, stale revision. |
| 2. Delete while preserving mirrors | Real Git: current/legacy worktrees removed; mirror, other environments' worktrees, files and historical references preserved. Typed confirmation checked in browser. |
| 3. Concise ticket | HumanTicket schema rejects over 700 words; six business sections/title; real ticket reviewed. Indicative 300–700 range: small changes may need fewer words. |
| 4. Continue same session | `test_v11_flow.py` and real request `local-id-removed`. |
| 5. Preserve versions | Three deterministic versions, two real versions, unchanged old content, immutable baseline, conflicting-tab updates rejected. |
| 6. Copy/export each version | Controlled and actual desktop/mobile workflows; ticket.md and goal.md for current/old versions. |
| 7. Actionable goal | Required sections, fixed constraints, actual baseline, expected tests and mandatory source verification; attachment references checked. |
| 8. Profiles available | Five internal profiles in database; read-only API. |
| 9. Targeted verification | Deterministic Reviewer → Code and Reviewer → Attachment; writing only after typed response; no open loop. |
| 10. Skills | Seven persisted definitions injected into relevant roles; PostgreSQL omitted without database. |
| 11. Dynamic pipeline | Simple: Requirement → Code → Writer in two invocations with combined Code/Writer. Files add Attachment; standard/complex/database add Reviewer. |
| 12. Read-only, no push, optional database | Linux sandbox, deterministic Codex/Claude workflows with resumption/versions; actual database SELECT allowed, DELETE denied, no secret in prompt, expired capability rejected. |
| 13. Standard latency/hard limit | Supervisor/budgets tested; actual timings below. Target is not a provider latency guarantee. |

## Migration and checks

- Pre-upgrade PostgreSQL backup: `.local/backups/spechelper-before-v11.dump`, permissions 0600.
- Restored to disposable PostgreSQL 17 and applied migrations 0003/0004: five results imported. Ticket JSON/Markdown identical, baselines retained, two artifacts per version. Existing and validation environments remained READY.
- Applied migrations to the instance after rehearsal; GitHub/ChatGPT still CONNECTED.
- Backend: **72 passed**, Django using PostgreSQL; one business integration test explicitly skipped without its dedicated DSN. Database path separately exercised by `runtime.database_smoke` on the disposable server.
- Ruff, migration check, Compose/Next.js build and TypeScript passed.
- Local browser: **12 scenarios passed**, desktop/mobile. Desktop Admin rerun successfully after correcting development-server trusted origin.
- Runtime isolation, Codex/Claude workflows and Codex database smoke passed. Deterministic CLIs read actual Bubblewrap worktrees and resumed the same session through a second version. They establish neither real-model quality nor speed.

## Real ChatGPT validation

Public project `public-validation-repository`, main, SHA `local-sha-removed`, no database. The existing environment was unchanged.

Simple request `local-id-removed`: clarify a tag-selection example for a beginner, changing help text only. References/syntax independently checked in `src/cli/args.rs` and `src/cli/sources.rs` at the baseline. Request worktree remained clean.

- Launch acknowledgment: **0.028 s**.
- First clarification: **22.281 s** job, including 20.020 s orchestration.
- After answer: **69.380 s**, READY v1.
- Discussion continuation: **48.774 s**, READY v2, same session `local-id-removed`.
- Version 1 unchanged and downloadable.

Clarification exceeded the 15 s ideal and initial simple processing exceeded the 60 s target. These deviations remain recorded. Targets are indicative; the hard limit is protected. Durations exclude human wait and distinguish queue from processing.

An initial standard request with an attachment exposed validation failure: the model decorated a filename with commentary. Publication was rejected without partial artifacts. The schema now restricts names to actual attachments, validated within bounded format repair. A regression test confirms one repair suffices.

After correction, standard request `local-id-removed` with `consigne-validation.txt` was **READY in 99.700 s**, acknowledgment **0.031 s**. It followed Requirement → Attachment → Code → Reviewer → Writer in four invocations, with no extra repair. The goal used the exact filename and baseline. This actual trial met the three-minute standard target.

Real v1/v2 exports were checked in Chrome on desktop/mobile: copied Markdown matched the selected version, filenames were correct, old goal unchanged, discussion history present, no overflow or JavaScript errors. Screenshots remain in `.local/screenshots/v11-real-*.png`.

On October 21, 2026, the user requested removal of the Agents and skills Admin tab. Profiles and skills remain internal orchestration details.
