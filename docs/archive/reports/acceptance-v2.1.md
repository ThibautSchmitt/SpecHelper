> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v2.1 acceptance review

Review date: 2026-10-23. Scope: conversational creation of declarative agents and
skills, human review and activation, shared-queue demonstration tests, restoration
and declarative import/export. Existing environment authorization, provider
adaptation and frozen analysis configuration remain part of the release boundary.

## Requirement evidence

This report records the final implementation and inspected terminal results.
Provider-response fixtures and real Linux isolation checks are distinguished below.

| ID | Requirement | Evidence and review status |
| --- | --- | --- |
| 21-01 | Agent/skill creation assistant available through authenticated administration | API tests reject unauthenticated access; English/French desktop/mobile flows open both generation actions, resume saved drafts and follow shared-queue links. Local-only access retains the existing loopback policy; authenticated shared-team sessions provide the remote administration boundary. |
| 21-02 | Conversational clarifications followed by declarative draft generation | Worker tests run clarification, a user answer, structured proposal and immutable draft history through the actual queue/orchestrator with controlled provider responses. |
| 21-03 | Preview, editing, human approval and activation remain distinct | API/browser tests retain inactive proposals, preserve edits after a version conflict, compare field changes, save drafts and require a separate human confirmation before library activation. Extra provider activation fields fail closed. |
| 21-04 | Deterministic schema, skill-reference, permission and provider checks | Independent API tests cover unsupported fields and versions, executable hooks, malformed expected checks, explicit write/secret/network requests including negation-prefix attacks, configured-secret rejection without echoing the value and provider intersections across required skills. |
| 21-05 | Global versioned definitions, environment authorization and provider adaptation | The full regression covers global library versions, environment reference selections and native Codex/Claude adaptation. Required skills must support the declared providers; disabled connection overrides block demonstration execution. |
| 21-06 | Generator receives no credentials and grants no write capabilities | Tests inspect minimized prompts, reject configured/recognizable credentials, discard unsupported proposals and retain central policy. No source, environment document, database, connection instructions or credential enters the generator context. |
| 21-07 | Demonstration execution writes only isolated temporary session files | Queue tests verify fresh independent runtime requests with empty source/attachment directories, no database or environment resources and frozen draft/skill versions. The real Linux probe confirms temporary-session writes, read-only sources, hidden credentials, zero capabilities, seccomp and blocked arbitrary egress. |
| 21-08 | Immutable history, restoration and preservation of historical configuration | Restore creates a new inactive version, preserves prior records and frozen request configuration, rejects stale versions and revalidates current skill references. Import preview does not create a library entry; imports remain inactive and updates require the current expected version. |
| 21-09 | Demonstration tests use the shared queue with visible execution status | Generation and demonstrations share ordinary Job claiming and account leases. Tests cover busy/queued/completed/error states, cancellation, stale-worker recovery, actual resolved model attribution, safe public metadata and deep-link resumption. A rejected model leaves other models on the same identity usable. |

## Validation results

Independent library API review: **31 passed**, including the focused migration
preservation test. Ruff passes for that review module. The tests also confirm that
expected checks reach compiled provider instructions and that remote library
operations require authentication and CSRF protection. The migration test preserves
all original fields in existing agent, skill, immutable revision and request rows,
including a historical configuration snapshot and agent-to-skill relationship.
New expected checks default to an empty list without changing old definitions.

Final integrated verification:

- Full backend suite: **585 passed, 1 skipped**. The host-only Linux skip is covered by the actual container probe. The existing Starlette test-client deprecation warning remains.
- Full desktop/mobile browser suite: **146 passed**. Four additional queue-localization cases were added afterward; all affected assistant/localization workflows were rechecked. The complete current browser inventory is 150 cases across that full run and focused checks.
- Final production-build access/library/model/assistant suite: **28 passed**, including the four new queue cases, English/French generation, import validation and historical restoration.
- Production build, TypeScript, Ruff and migration drift checks pass. Migration 0025 was applied to a protected database copy; original values in **34 tables and 384 rows** were unchanged.
- The real Linux runtime probe again denies source writes, credential and other-session access, arbitrary network and unsafe broker destinations, including README, PDF, ticket and database injection carriers. It confirms UID/GID 10001, zero capabilities and enforced seccomp.
- Gitleaks finds no candidate secrets. Semgrep runs six local rules over **153 production files**, including all new assistant/validation files, with no findings or parse errors.
- CI includes the new assistant browser workflows alongside access, library and model checks.

Provider calls in
deterministic tests use controlled responses; these do not establish live account
entitlement or paid-inference success. Actual-provider runs, production deployment
and publication must be reported separately when performed.

## Scope and interpretation

The release creates configuration, not executable extensions. Free Python/Bash/JS
execution as a skill, repository or business-database writes, automatic extension
installation and automatic activation are excluded. A generated instruction cannot
override the runtime's central policy. Explicit requests to obtain credentials,
contact arbitrary destinations or access another environment are rejected or
neutralized before activation.

One instance remains a trusted shared team. The shared access session does not
identify an individual administrator. Existing analyses retain their original
configuration snapshots when the library changes. A restore creates a new inactive
revision and must pass current checks; imports also require explicit activation.

The [library guide](../guides/ai-library.md) explains the administrative workflow, provider
limitations and declaration lifecycle. The existing [security acceptance review](acceptance-v1.9.md)
still applies; this feature review does not certify a different host or remove
documented operating-system dependency conditions.
