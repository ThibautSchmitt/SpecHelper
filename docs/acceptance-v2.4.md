# v2.4 acceptance evidence

Status: implementation and controlled integration checks passed. This report separates controlled
application behavior from actual provider quality and capacity measurements.
No live inference or production deployment is implied by an application test.

## Requirement boundaries

| Requirement | Required evidence |
| --- | --- |
| V24-01: one queue schedules ready compatible steps | Oldest runnable job selection, role restrictions and blocked-head bypass. |
| V24-02: sequential mandatory roles per job | Atomic attempt ownership, cached checkpoint replay and Analyst/Counter-analyst/Verifier order. |
| V24-03: different jobs progress concurrently | Overlapping actual test invocations on distinct connections with no same-job overlap. |
| V24-04: atomic shared capacity | Competing claims and known shared account/quota exclusion. |
| V24-05: clarification releases capacity | No reserved invocation while waiting for the user; stable job identity on answer. |
| V24-06: cancellation and restart preserve history | Process cleanup, stale attempt fencing, retained checkpoints and single publication. |
| V24-07: no business deadline | More-than-five-minute execution remains active; technical limits remain visible. |
| V24-08: global lazy skills | Discovery across two providers without assignments, on-demand contents and actual loaded-version audit. |
| V24-09: skill editing and assisted creation | Existing CRUD/history, explicit activation and generation workflows. |
| V24-10: two configurable instruction levels | Global and connection fields; environment factual resources preserved. |
| V24-11: mandatory permissions and role missions | Attempts to override sandbox access remain rejected or ineffective. |
| V24-12: independent omission discovery | True initial claim plus decisive omitted exception, independently found before comparison. |
| V24-13: verifier reviews omissions and limits | Explicit concern resolutions, actual Git/SQL evidence and unresolved material limits. |
| V24-14: honest activity states | Role, stage, active connection, actual elapsed time, wait reason and terminal state; no invented percentage. |
| V24-15: immutable execution context | Git/environment/configuration, connection instructions and actual loaded skill versions preserved. |

## Independent omission checks

The controlled omission corpus uses an actual committed synthetic cancellation
guard. Its ordinary rule is true, while a migration branch changes cancellation
behavior. The Counter-analyst receives neither the initial Analyst's private marker
nor its current findings during its first exploration. The comparison then exposes
both reports and explicit coverage concerns to the Verifier.

The focused tests cover both Questions and Requests:

- Supported initial claims do not waive missing or unverified coverage resolutions.
- Invented final claim identifiers cannot close a material concern.
- A discovered exception reaches final qualified evidence and all result artifacts.
- A missing supported resolution forces a partial blocking result.
- A material unexplored caller remains a visible verification limit.
- An essential omission newly found by the Verifier cannot disappear from its report.
- A material business choice requires an explained question before final writing.
- Guided **Other** answers preserve the job identity, reuse completed independent
  explorations and appear in the final answer or ticket artifacts.

These checks use controlled provider responses and real frozen Git provenance.
They verify orchestration and evidence preservation, not autonomous model recall,
general factual accuracy or exhaustive repository coverage. Database minimization,
counterexample execution and absence/unavailability reporting retain the v2.3
validation requirements.

Run the focused protocol checks with an isolated PostgreSQL test database:

```sh
cd backend
uv run pytest -q tests/test_v23_flow.py tests/test_v24_omissions.py
```

## Completed integration evidence

- The final complete backend suite passed **732 tests**, with one existing host
  capability skip, in 181.10 seconds. This includes the final lazy-file redaction,
  public retry, database-enabled workflow and runtime integration changes.
- Additional public retry checks cover Requests/Questions, rejected duplicate clicks,
  preserved job/run/baseline and fresh attempt contexts.
- A full database-enabled workflow executes a real read-only PostgreSQL counterexample
  count and retains its trusted query receipt in the final scoped evidence. SQL skills
  are exposed only in steps with database access, including no SQL skill in initial
  clarification or final writing.
- Real PostgreSQL tests use independent worker connections and runtime barriers:
  two jobs/providers/environments overlap, same-job and shared-account duplicate
  claims are rejected, and the oldest compatible job bypasses a blocked head.
- Fresh heartbeats keep an execution active after its recorded start is aged beyond
  eight minutes. This is an age/guard check, not a measured eight-minute provider run.
- Cancellation and orphan recovery retain capacity without a positive remote stop
  acknowledgement. Late output, progress and run-state writes are fenced; resumed
  checkpoints keep their job/run and publish exactly one immutable result.
- Migration checks preserve factual environment resources, connection text and
  original library revisions. Pending old queue entries retain IDs and payload
  content while gaining a transition marker. Claiming them retains reusable typed
  observations, the old context for audit and known family history; unqualified
  source reports are rechecked. Unsafe or role-specific old text remains for review.
- **128 distinct desktop/mobile browser scenarios** passed across the combined run
  and targeted rechecks, covering English/French, themes, global settings, loaded
  skill/instruction history, parallel cards, cancellation, retry and migration notices.
- TypeScript, the production frontend build, Ruff, Compose configuration and migration
  generation consistency passed. Gitleaks found no candidate secrets; six Semgrep
  rules scanned 179 production files with no findings or parse errors.

### Actual Linux isolation

The freshly built runtime image ran `python -m runtime.v24_smoke` without provider
credentials or external network access. Two Bubblewrap sandboxes overlapped while
keeping sources, attachments and writable sessions separate; source writes failed.
Authorized Git history remained readable while unrelated repository caches and
other jobs' linked-worktree metadata remained hidden.
Kernel file-read observations recorded only the procedure actually read, including
its exact version/hash. Cancelling an exact attempt stopped its process and child,
ignored a mismatched attempt and remained idempotent.

The existing `runtime.v19_smoke` additionally passed material capability, seccomp,
credential, arbitrary-network, provider-broker and hostile-document boundaries.
These are actual Linux probes using synthetic data, not model-inference checks.

### Limits of these observations

Provider workflow outputs and cancellation responses in application tests are
controlled. These checks establish scheduling, evidence handling and isolation;
they do not measure autonomous model accuracy or live subscription throughput.
The independent native v2.3 comparison now has six completed paired analyses and
actual duration/token measurements. Its strict quality gate failed on exact-source
citation defects; see [the v2.3 report](acceptance-v2.3.md). Cost remains unknown.
These separate observations do not imply a shared-instance deployment or change
the controlled nature of this v2.4 report.
