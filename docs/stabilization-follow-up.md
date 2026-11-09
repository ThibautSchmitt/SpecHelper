# Stabilization follow-up — 8 November 2026

This supplements the [7 November measurements](stabilization-final.md). It does
not replace their historical observations or declare the release fully qualified.
The requested order is CI repair, real qualification, then measured optimization.
Product UI changes and external ticket editing remain deferred.

Newer evidence is recorded in the [9 November qualification](qualification-20261109.md),
including native cancellation/restart, worker process reclamation and additional
real GitLab/GLPI publications. Its tool-error and quota limitations remain explicit.

## CI and Linux security repairs

Commit `86b7692daa8e008363ed250e1dc278359cb507a8` passed both complete hosted
campaigns: [Checks 42466160963](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42466160963)
and [Security campaign 42466160999](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42466160999).
Backend, desktop/mobile browser checks, source scans, all three image gates and
DAST succeeded. No check was disabled to obtain this result.

The subsequent application commit `150b5f77952619b5a2ef30a362d318884e88b5d5`
also passed the complete [Checks 42468822903](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42468822903)
and [Security campaign 42468822961](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42468822961):
**1,739 backend tests passed** (one deprecation warning), both browser viewport
suites passed, and all source/image/DAST gates passed. This commit includes the
conversation-read optimization measured below and was pushed to `main`.

- Backend CI installs the `rg` executable required by its evaluation tests and
  allows 25 minutes for the complete suite. A capability test now supplies its
  own SQL-requiring skill rather than assuming the built-in privacy skill needs SQL.
- Browser regressions were updated to the existing compact settings, activity,
  report and ticket interfaces. No product UI was redesigned. The two viewport
  suites run separately and retain JSON reports and failure artifacts.
- The oversized-body TLS probe accepts an early TCP reset only while still
  requiring the actual HTTP 413 response. The disposable HTTPS probe passed its
  access, cookie, CSRF, origin, logout, redirect and size assertions.
- All three images receive the explicitly pinned signed library fixes. The
  backend rebuilds the upstream GitHub CLI with the patched Go networking module
  and retains upstream licenses. Exact Debian-package conditional reviews remain
  visible and expire on 22 November; a passing gate is **not** a zero-CVE claim.
- An independently checked Docker archive binding resolves the OCI-index versus
  config-digest mismatch without accepting arbitrary different images.
- The runtime uses the same packaged bubblewrap binary at `/usr/local/bin/bwrap`.
  This avoids an Ubuntu host desktop AppArmor profile attaching to `/usr/bin/bwrap`;
  sandbox permissions, seccomp, source mounts and role isolation are unchanged.
  The hosted Linux namespace and native-transport material-control probes passed.

See [security testing](security-testing.md) for the controls, exact package reviews
and image-evidence rules. Synthetic transport probes are not native-provider tests.

## Actual local qualification

Hardware and scheduler limits are the same as the previous report: Intel Mac,
32 GiB host RAM; Docker VM with eight CPUs and about 7.67 GiB RAM. Native runtime
limits remain two CPUs, 2 GiB and 256 tasks, with a 128-task sandbox UID budget.
Two native invocations can run concurrently; excess requests queue.

Only existing roles were used: ChatGPT has the three analysis roles; Antigravity
has Counter-analyst only. No role or quota was changed for the tests.

| Actual native batch | Complete | Response latency min / median / max | Isolation |
| --- | --- | --- | --- |
| Five conversations | 5/5 | 28.75 / 57.764 / 85.894 s | Five distinct contexts and sessions; own marker only |
| Ten conversations | 10/10 | 27.927 / 88.236 / 149.626 s | Ten distinct contexts and sessions; own marker only |

These are elapsed submission-to-completion times, including the two-slot queue.
They are not p95/p99 capacity guarantees. Questions used non-sensitive SpecHelper
sources and did not create tickets or start deep analyses implicitly.

The endurance plan reused those ten conversations over five waves spaced 30
minutes apart. Only its first wave completed. Two additional independent deep
analyses started and retained their frozen Git references and separate Analyst
contexts. The provider then reported its session quota exhausted, resetting at
14:26:12 UTC. The deep analyses stopped before all required roles completed.
No text produced by a model was accepted as proof that the other roles ran.

The test clients were stopped and only their outstanding jobs cancelled through
normal APIs. Observations were preserved. This is **not a successful two-hour
endurance test or a completed three-role concurrent qualification**. Active native
cancellation and inference after restart also remain unqualified; queued
cancellation succeeded. The executable endurance command below allows a rerun
when quota is available.

## Two confirmed real publications

The user explicitly approved the two neutral test tickets before external writes.
Both existing connections published concurrently, each to an already authorized
environment/destination; no environment association was changed. No documents,
sensitive content or implementation work were attached.

| Connection | Destination | Confirmed external reference | Browser link |
| --- | --- | --- | --- |
| GitLab | `test/test` | work item 2 | `http://localhost:9082/test/test/-/work_items/2` |
| GLPI | `Root entity` | ticket 3 | `http://localhost:9080/front/ticket.form.php?id=3` |

For each publication, two simultaneous confirmations using the same operation key
and a later repeated confirmation returned the same local publication. There is
one publication record and one permanent conversation event per ticket. The active
draft was released. Both links opened successfully (HTTP 200), appeared in Tickets,
and persisted after page reload and conversation archival. The existing browser
resolver maps the recorded Docker-only GLPI host alias to localhost; stored
publication evidence was not rewritten.

These tests establish two actual provider connections, not 5–10 distinct real
accounts or verified ownership by separate people. GitHub/Jira real writes,
attachment delivery and lost-response reconciliation against a real provider were
not exercised. The previous controlled concurrent HTTP/PostgreSQL tests cover
those contract scenarios, with their simulation limits still applicable.

## Restart and resource observations

After checking that no AI job remained queued or running, backend, worker and
runtime were restarted. Hashes of messages, recorded session metadata, Git
baselines, publications and active drafts for 17 test conversations were identical
before and after restart. API health recovered. A Linux process snapshot contained
only init, Uvicorn and the probe: no native CLI or zombie, no OOM kill or PID-limit
event. Persisted state is verified; successful new inference after restart is not,
because the provider quota was unavailable. Twenty test conversations were archived;
their histories and the two external tickets were retained.

The sampler recorded 75 observations from 09:25:51 to 09:47:47 UTC with no sampling
errors. It includes load, quota waiting, cooldown and the controlled restart:

| Measurement | Observed value / limitation |
| --- | --- |
| Six core services, total sampled RAM peak | 1,265,914,348 bytes (about 1.18 GiB) |
| Runtime sampled RAM peak | 492,201,574 bytes (about 469 MiB) |
| Runtime task/thread peak | 133; below the container limit, not one sandbox's task count |
| Five-conversation window, runtime CPU mean / peak | 33.82 / 122.46%, five samples |
| Ten-conversation window, runtime CPU mean / peak | 17.75 / 54.07%, nine samples |
| Zombies in sampled Linux snapshots | 0 |
| Current image sizes: backend / frontend / runtime | 415,669,031 / 296,484,619 / 2,063,986,779 bytes |

CPU percentages are relative to one core. Sparse samples can miss peaks; batch
means are not evidence that ten conversations are cheaper than five. The end of
the ten-conversation window overlaps explicit deep-analysis context preparation.
Connector-lab containers are excluded from core-service totals. No controlled
application-wide RAM, image-size or throughput improvement is claimed.

During earlier image builds/scans, the 59 GB Docker VM filled and PostgreSQL
temporarily entered recovery. Owned build/scan work was stopped; only identified
test cache resources were removed. PostgreSQL recovered and was backed up before
the native tests. About 2.5 GB remained free during qualification. Host free space
does not establish free space inside Docker's VM. Avoid additional builds or image
exports until enough VM space is available; no global prune or shared-data purge
was used. This operational incident is not attributed to normal conversation load.

## Measured conversation-read optimization

A disposable PostgreSQL fixture contains 1,000 messages and 20 historical cycles.
Five fresh reads are measured per variant, including JSON encoding. Reusing the
same latest cycle/result within one response eliminates repeated heavy JSON-row
loads in revision, decision and result projections. No endpoint, history content,
session behavior or UI changed; no migration or new service is required.

| Same fixture | Before | After |
| --- | --- | --- |
| SQL queries per complete read | 35 | 31 |
| Latest cycle / result reads | 2 / 3 | 1 / 1 |
| Median complete read including JSON | 193.44 ms | 183.58 ms |
| Complete response size | 1,286,060 bytes | 1,286,060 bytes |
| Initial / unchanged progress response | 114 / 66 bytes | 114 / 66 bytes |

The timing change is modest and environment-dependent; the four removed queries
are deterministic. Existing incremental progress polling was retained. The new
regression test verifies all 1,000 messages, all 20 cycles/results, the latest
summary and small unchanged-progress responses. The 88 affected PostgreSQL tests
passed; Ruff passed. No speculative frontend/polling refactor was introduced.

The load probe now supports `--reuse-conversations --interval-seconds 1800`.
A controlled HTTP fixture verified two waves reusing five conversations (ten
responses, zero native inferences); it is separate from the actual provider results.
Run commands and remaining acceptance criteria are in
[local administration](local-administration.md#controlled-and-real-load-tests).

## Local deployment — 8 November 2026

The optimized application backend and worker were rebuilt and recreated at
10:17 UTC. The running image is
`sha256:c6807152979cf790e82b907b73b9d77b592d14fd0207a2892505a9a48d1d3400`
(415,678,086 bytes). Its three optimized Python source files have the same SHA-256
digests as the checkout. Frontend and native runtime application behavior did not
change in this backend-only deployment. No database migration was pending.

Before replacement, an application PostgreSQL custom-format backup was verified
(1,844,575 bytes; SHA-256
`e79d9112da8d339210d165486ca8bee4dda331aa2e7efc9c9700b0f3dd62c870`).
The previous backend image remains tagged locally for rollback; persistent volumes
and encryption/control keys were retained. No active AI job was interrupted by
service replacement.

The low-space rebuild first tried putting both Go module and compiler caches in
memory. That attempt was cancelled after memory pressure temporarily stalled
Docker and the application. It was not deployed. The final Dockerfile keeps only
the compiler cache in memory, uses two compilation workers, and removes downloaded
modules from the build layer after retaining their licenses. The completed build
took 342 seconds; the monitored minima were 1,126,957,056 free disk bytes and
1,156,993,024 available VM-memory bytes. Its compiler step retains a 40.73 MB build
record rather than the previously observed 1.55 GB cache. Specifically
identified, unused, non-shared SpecHelper CLI build records (about 922 MB) were
removed; no global cache prune, application-data deletion or shared-resource cleanup
was performed. About 2.6 GB remained free after deployment.

Post-deployment checks:

- Compose reported the backend healthy; the worker started and reached the native
  runtime. `/api/health` returned HTTP 200 and Django reported no system-check issue.
- Exact-image applicability checks all passed, including non-root execution,
  no privilege escalation and fixed library versions. Both upstream licenses are
  present. The rebuilt GitHub CLI executable has the same SHA-256 digest as the
  previously validated executable.
- Counts were preserved: 83 conversations, 291 messages, 50 analysis runs, 24
  results, 11 conversation tickets, four publication records and 227 AI sessions.
  Content/source/session hashes matched the pre-deployment state. Only three older
  conversations' archive timestamps changed during the observation window; this is
  recorded separately from content preservation, without attributing its cause.
- The 17-conversation restart fixture remained identical. The real GitLab and GLPI
  publication links still passed the browser/reload checks after deployment.

No additional provider inference or external publication was performed for this
deployment. The quota-related qualification limits above remain open.
