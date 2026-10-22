> Public version: session/request identifiers and instance references are anonymized. Original evidence remains local.

# SpecHelper v1.2 acceptance — October 21, 2026

v1.2 was installed at `http://localhost:3000`. v1.0/v1.1 audits remain historical evidence. This report predates the English/French language feature; its test counts do not validate that later feature.

## Overriding product decision

The user requested a business-user application and removal of agents/skills from Admin. No tab, form or advanced analysis options expose these mechanisms. Roles, skills and enabled flags remain internal. This deliberately replaces the earlier proposal to expose internal settings. Safety contracts and essential workflow steps cannot be disabled.

## Coverage of all 18 sections

| Section | Implementation and evidence |
|---|---|
| 1. Purpose/scope | Shared team instance, no accounts/private spaces; business form and guided connections. |
| 2. Architecture | Next/React/TypeScript/shadcn/Tailwind, Django/Ninja, PostgreSQL, persistent worker, Git and isolated Docker runtime preserved. |
| 3. Admin | Connections, Environments, Instance; name/label/color retained. Internal settings removed by product decision. |
| 4. Environments/Git | Revision-guarded create/edit, sync and confirmed deletion; N repositories, shared mirrors, worktrees and frozen baselines. test_v11_environments.py and test_git.py. |
| 5. PostgreSQL | Host/masked URL, single test button: connection, SELECT 1 and read-only rights; three statuses. v1.2 tests and actual PostgreSQL. |
| 6. Business cycle | Environment, need, files, comparison checkbox; clarification before full exploration, same Request resumed. Workflow/browser tests. |
| 7. Ticket/goal | Format 1.2: brief context, separate need/expected behavior, concise ticket; technical goal with sources/SHAs/constraints/criteria/tests. Two actual outputs inspected. |
| 8. Discussion | New message, same contexts, new immutable version, old copies/downloads preserved. Two actual continuations. |
| 9. AI connections | Independent Codex/Claude, enabled/availability distinct from authentication, bounded selection/fallback; unavailable quota/reset remain unknown. |
| 10. Comparison | Independent analyses, synthesis in third context; two providers or two sessions of one provider. Both modes deterministic; actual single-provider trial. |
| 11. Agents/skills | Five profiles/seven skills; internal flags, no Admin exposure. Tests preserve mandatory contracts. |
| 12. Orchestration | Structured contracts, useful roles only, one targeted verification, bounded format repair; ten calls and two provider attempts per job execution. |
| 13. Queue/performance | Shared persistent queue, default sequential worker, understandable capacity wait/progress; 285 s orchestration and 295 s process supervision. |
| 14. Security | Read-only workspaces/files/cache, separate contexts, credentials outside prompts, filtered read-only PostgreSQL, no commit/push. Actual Linux/database smokes. |
| 15. Data model | Multiple connections; sessions per Request/role/provider, context UUID, compatible primary link, comparison mode/immutable formats; migrations 0005–0006. |
| 16. Requirements | FR matrix below. |
| 17. Acceptance | Ten criteria below, distinguishing deterministic/actual trials. |
| 18. Exclusions | No similar-request search, feedback, developer review, advanced database diagnostics, automatic PRs, proprietary graph or advanced scheduler. |

## Functional requirements

| Requirement | Verification |
|---|---|
| FR-01 | Environment CRUD API/UI, revision-guarded edit/delete; validation environment created, renamed, synchronized and deleted. |
| FR-02 | Multiple repositories/branches and optional database; existing environment kept two repositories; connected trials used no database. |
| FR-03 | Git reuse/deletion tests; validation mirror still present after environment deletion. |
| FR-04 | Browser: one Test connection button in database form, no separate diagnostic step. |
| FR-05 | SELECT 1/permission checks, role with UPDATE rejected on actual PostgreSQL; only three indicators, no secret in response. |
| FR-06 | Two connection cards, distinct login sessions, connection-specific test; API/browser tests. |
| FR-07 | Exhausted quota excluded, automatic selection/fallback, no cross-provider SID reuse; queue retained without capacity. |
| FR-08 | Checkbox sent at creation, mode frozen in Request; Instance permission applies only to new requests. |
| FR-09 | Single/dual-provider tests: three contexts, B cannot see A's conclusions, synthesis receives both; two versions/resumption for all three roles. |
| FR-10 | Adapted to explicit user request: internally configured/enabled profiles/skills, no Admin settings. |
| FR-11 | test_clarification_resumes_same_session and Linux smoke: question/answer/same SID and Request. New connected trials were precise enough to avoid clarification. |
| FR-12 | Actual v2 tickets: 238/220 words, two-sentence context, no reasoning narration, scope limited to adding one sentence. |
| FR-13 | Actual goals: 408/404 words, baseline/files/symbols/constraints/criteria/tests/exact attachment reference. |
| FR-14 | Two continuation messages, two new READY versions without recreating Requests; same four SIDs before/after. |
| FR-15 | v1 saved before continuation compared with API/exports after v2; v1.1 history still readable. |
| FR-16 | SHA local-sha-removed identical across versions, rename and environment deletion. |
| FR-17 | Simultaneously submitted analyses executed sequentially; reservation/release, distinct requests and crash recovery tested. |

## Ten acceptance criteria

| Criterion | Conclusion and evidence |
|---|---|
| 1. Edit/worktrees | Edit/configuration/source-preservation tests; actual rename at revision 2 followed by READY. |
| 2. Delete without losing shared cache | Two environments sharing one mirror; actual validation deletion preserves mirror/requests. |
| 3. No-database analysis | Four connected executions READY without business connection. |
| 4. Simple strict database test | Three UI statuses; actual PostgreSQL permits read then rejects role after UPDATE grant. |
| 5. Two providers/selection | Independent configurations/selection/fallback tested. Real available account: Codex; Claude disconnected, no claim of actual dual-account selection. |
| 6. Single/dual comparison | Both modes pass with deterministic CLIs on Linux; actual single-Codex analyses/synthesis and continuation. |
| 7. Ticket shorter than goal | Standard v2: 238 vs 408 words; comparison v2: 220 vs 404. |
| 8. Actionable goal | All eleven sections, exact baseline, paths verified at SHA, minimal-change constraints and independent verification. |
| 9. New version after message | Both Requests v1 → v2 READY, same SIDs, v1 unchanged/exportable. |
| 10. Under five minutes | Actual standard jobs 89.2/69.7 s excluding queue; comparison 134.0/94.5 s. Global supervisor stop tested at 295 s. |

## Connected trials and evidence scope

Temporary environment: public-validation-repository, main, SHA above, with `cadrage-validation.txt`. Need: add an exact long-help sentence without changing examples, other messages, options, behavior or database. Independently read `src/cli/args.rs`, `src/main.rs`, `src/crontab.rs` and `src/crontab/parser.rs` at the SHA. The --tag example and Running... output are in long_help_message(). Both analysis worktrees remained clean.

| Request | Acknowledgment | Analysis v1 | Continuation v2 | Contexts |
|---|---:|---:|---:|---:|
| local-id-removed standard | 0.033 s | 86.8 s | 66.8 s | 1 |
| local-id-removed comparison | 0.026 s | 131.6 s | 92.0 s | 3 |

Analysis durations come from AnalysisRun; criterion 10 also includes job preparation. Launch-to-reservation waits are excluded from analysis. Four SIDs/context UUIDs stayed identical after continuation. Goals limit implementation to the need and explicitly require independent source verification.

The 15 s question/60 s simple-request objectives are targets, not guarantees; these attachment trials do not measure them. Latency depends on providers. Deterministic CLI results never measure real-model quality or speed.

## Automated checks

- Backend: **89 passed**, Django on PostgreSQL and disposable business DSN configured; no PostgreSQL skips. Ruff, migration completeness and frontend typecheck passed.
- Local browser: 20 desktop/mobile scenarios passed before final internal-settings removal; eight v1.2 scenarios passed again after removal. Fixtures never target the deployed instance.
- Actual Linux: runtime.smoke, normal Codex/Claude workflows, single-Codex/single-Claude/dual comparison passed. Fake CLIs read real Bubblewrap worktrees and verify mount isolation/SID resumption.
- Sandbox PostgreSQL: dual deterministic comparison passed with reads allowed, DELETE rejected, no secret in prompts and capability expiration.
- Deployed UI: actual results, copies/downloads of current/old versions, old v1.1 result and absence of internal Admin settings checked on desktop/mobile.

## Migration and preservation

Pre-migration backup: `.local/backups/spechelper-before-v12.dump`, mode 0600. Restored into disposable PostgreSQL, applied migrations 0005–0006 and compared fingerprints of nine historical field sets. Repeated on the deployed instance: all nine identical, covering 9 Requests, 9 ResultVersions, 18 GeneratedArtifacts, 9 AISessions, the existing environment/two repositories, zero business databases, GitHub and Instance settings. New fields excluded. Legacy sessions retain filesystem contexts and gain provider links. Final comparison after all acceptance trials, excluding only the two validation requests and their sessions/versions/artifacts, again matched all nine fingerprints.

Previous worker stopped only after checking no active job. Trials added two Requests/four versions without replacing existing requests. Temporary environment deleted after analysis; existing environment remained the only environment with unchanged SHAs. Cache/validation artifacts retained for review.

## Recorded limitations

One worker runs jobs sequentially: different browsers can submit requests, without parallel execution. Data/connections are shared; no private spaces/application accounts. Existing guards reject concurrent operations on the same request.

Claude was not connected, so real Claude authorization and comparison across two actual accounts are not declared validated. Its adapter/contracts/isolation/dual selection are covered deterministically. No official quota/reset information is invented.

## Fix after prolonged use — October 21, 2026

A comparison with only ChatGPT available remained queued after clarification. Its first stage had succeeded. The runtime container accumulated 252 zombie Bubblewrap processes and reached 254 tasks against a 256 limit; even docker exec could not start and isolation health checks failed. The connection was marked ERROR, blocking the queued job.

The runtime service now uses init: true to reap orphans. Only that container was recreated; volumes, answers and sessions were preserved. After a successful ChatGPT check, the existing job resumed with the same Request/clarification answer.

Regression: runtime.process_smoke performs 300 isolation checks. Without init, a disposable container reproduced unavailability before completion; with init and the same 256 limit, all 300 passed with zero zombies before/after. Another run on the deployed runtime confirmed no process growth. Ruff and docker compose config --quiet passed. No analysis budget or provider-selection change.

The affected request, local-id-removed, completed both single-Codex analyses and synthesis in three contexts about 176 seconds after resumption. Jobs 32/33 are DONE. Its first ticket/goal version is PARTIAL: the expected business model/relation was not found in examined sources, and that uncertainty is explicit. Runtime returned to three idle tasks with no zombie accumulation.
