# Stabilization qualification — 7 November 2026

This report separates executed tests, controlled fixtures and real provider work.
The release is not declared stable merely because unit tests pass.

## Test configuration

Host: Intel MacBookPro16,1, 32 GiB RAM, 16 logical CPUs. Docker Desktop engine
24.0.5: 8 VM CPUs, 8,240,328,704 bytes RAM, overlay2. Runtime limits remain 2 CPUs,
2 GiB and 256 container tasks; sandbox UID tasks are bounded to 128. The global
scheduler and runtime each admit two AI invocations; other conversations queue. Native
conversation connection: existing ChatGPT/Codex configuration, independent session
homes, unchanged roles. No Antigravity role was granted.

Database integration tests use a separate PostgreSQL 17 container with loopback
port, 768 MiB limit and 512 MiB tmpfs data. No personal application data is used
by destructive tests. Docker cleanup is exercised on another explicitly named
disposable Compose installation, alongside the real installation and an external
shared volume.

## Measurements and targeted fixes

| Measurement | Baseline | Changed behavior / verification |
| --- | --- | --- |
| Six-sample total memory peak without native AI | 867,161,866 bytes (827 MiB) | After native batches: 1,090,781,185 bytes (1,040 MiB); different warm-cache/image states, no idle-RAM gain claimed |
| Native mutex entries after 1,000 isolated invocations | 1,000 | 0 |
| Tracemalloc retained bytes in that same fixture | 425,730 | 5,354 |
| Queries to render links for 20 publication rows | 21 | 1 with connector eager loading |
| Bubblewrap endurance | 300 real Linux probes | 0 zombies before and after |
| Runtime cgroup counters during investigation | 0 OOM kills; 0 container PID-limit hits | Does not rule out the separate shared UID task limit |

The mutex fixture returns before native inference; this is a small metadata
retention fix, not an application-wide RAM reduction claim. Publication query
counts are measured through Django's query capture. Existing incremental browser
progress polling was retained. There is no speculative worker-count increase,
new cache service or replacement session architecture.

The initial real five-conversation batch produced three early errors, one answer
and one stuck native tool operation. That operation was subsequently cancelled
through the normal API; its lease was released and the runtime returned to no
native CLI processes and no zombies. A later Docker Desktop dashboard failure
accumulated blocked Docker-statistics clients, made the engine/API unresponsive
and interrupted the measurement transport. This is not a successful load result.
The dashboard was closed and Docker restarted without a volume reset. Sampling
windows taken before approval/startup or during builds cannot be labelled as
five-CLI load metrics.

Two admissions alone were insufficient: a subsequent ten-conversation batch
completed six responses and left two native operations blocked, with two more
queued. A real parallel Linux probe failed with `BlockingIOError: [Errno 11]
Resource temporarily unavailable`, while cgroup OOM/PID counters remained zero.
Native process snapshots showed that one Codex process could use 37 threads,
in addition to its code-mode helper and relay. Linux applies RLIMIT_NPROC across
the shared UID, including threads and separate PID namespaces.

Both the relay and syscall-boundary task limits were therefore aligned to 128,
below the unchanged container limit of 256. The global scheduler default was
aligned to two slots, avoiding repeated worker starts for rejected runtime slots.
The interrupted batch was cancelled through the normal API and its failures
retained. The final native batches below use the calibrated configuration.

## Final native batches

| Batch | Completed / submitted | Errors / cancelled / pending | Distinct contexts / native sessions | Response latency min / median / max |
| --- | --- | --- | --- | --- |
| Ten conversations | 10 / 10 | 0 / 0 / 0 | 10 / 10 | 27.10 / 76.31 / 123.38 s |
| Five further conversations, same configuration | 5 / 5 | 0 / 0 / 0 | 5 / 5 | 24.36 / 46.73 / 69.82 s |

Every response included its own unique test marker; none contained a marker from
another conversation. Account selection/roles were unchanged. These were real
Codex invocations against frozen SpecHelper sources, not simulated model outputs.
The additional five-conversation batch exercises repeated native cycles after
the ten-conversation load. It is not a multi-hour endurance qualification.

Resource samples are cut to each batch's actual timestamps; the combined sampler
also covered cooldown intervals, which are excluded from load means.

| App measurement | Ten-conversation window (22 samples) | Five-conversation window (13 samples) |
| --- | --- | --- |
| Total sampled memory peak | 1,264,519,741 bytes (1.18 GiB) | 1,322,799,596 bytes (1.23 GiB) |
| Runtime sampled memory peak | 554,591,846 bytes | 572,627,354 bytes |
| Worker sampled memory peak | 260,990,566 bytes | 321,073,971 bytes |
| Runtime CPU mean / peak | 36.53 / 173.95% | 6.11 / 27.08% |
| Worker CPU mean / peak | 33.80 / 218.85% | 47.15 / 207.82% |
| Runtime task/thread peak | 122 | 109 |

CPU percentages are relative to one core; sampled peaks are not hard instantaneous
maxima. Scheduled Git checks and normal health/inventory work remain enabled.
The earlier incomplete ten-conversation window recorded worker CPU mean 108.67%,
peak 527.55% and memory peak 489,789,850 bytes. Its outcome and duration differ:
this is operational before/after evidence, not a statistically controlled speedup.

After completion, the Linux runtime snapshot contained only init, Uvicorn and the
probe itself: no native CLI, no zombie, no OOM kill and no container PID-limit hit.
The zero-active-AI-job check also passed. Native state remains persisted on disk
for legitimate continuation; memory/page cache is not expected to return to a
freshly restarted image's value immediately.

## Executed verification

- Final full PostgreSQL backend suite: **1,727 passed, 6 skipped**, zero failures
  and errors, in 735.8 seconds. Five optional business-database integration tests
  lacked their dedicated disposable database configuration; one kernel read
  observation test requires Linux. They are not counted as successful checks.
- Final focused PostgreSQL checks: **38 passed** (including six repeated 5/10
  account HTTP batches), then **11 passed** for the latest deletion/query checks.
  Capacity/provider checks after changing the default: **30 passed**.
- Runtime/security targeted checks: **43 passed**. The Linux parallel probe with
  two 35-thread workloads passed with read-only sources, hidden foreign
  repositories/session data and exact-attempt process-tree cancellation.
- Browser retirement flows: **10 passed**, desktop/mobile and French/English,
  covering explicit confirmation, one-publication removal, asynchronous session
  cleanup, preservation of other cycles/messages and no deletion action before a
  cycle exists. API responses are fixtures.
- An exploratory restricted-sandbox run could not bind local TCP/Unix sockets;
  those permission failures are not application regressions. The concerned
  connector/gateway/runtime checks were rerun with socket access: **101 passed**.
- TypeScript check and production frontend image compilation passed.
- Real disposable Docker stop/start, clean/restart, purge/reinstall and a second
  purge passed. Data survived clean, did not survive purge, external shared volume
  survived both purges, and the main installation's container IDs were unchanged.
- A cold backend build exposed an unavailable pinned GitHub CLI APT version.
  The pin and exact installed-version check were updated to the version present
  in GitHub's signed APT repository; the images then built successfully. This
  does not guarantee perpetual availability of upstream packages.

The controlled HTTP load completed **45 confirmed publications**: three batches
of five and three batches of ten distinct synthetic accounts. All used the chosen
account/destination and frozen source; lost creation responses reconciled without
another creation. Duplicate and isolation-error counts were zero. Per-operation
latencies were 0.66–1.14 s for five-account batches and 1.14–20.87 s for ten-account
batches. These are fixture timings, not real-platform SLAs. Earlier fixture errors
observed during concurrent builds are retained in the private test log.

The existing real GitLab publication was read after deployment: one conversation
entry after reload, unchanged external reference and direct URL. Opening it reached
the provider's sign-in page. No new external issue was created during this campaign.

## Image and disk inventory

| Image | Before rebuild | Final rebuild |
| --- | --- | --- |
| Backend | 362,468,530 bytes | 413,874,808 bytes |
| Agent runtime | 2,067,659,263 bytes | 2,060,085,925 bytes |
| Frontend | 413,076,054 bytes | 293,080,502 bytes |

Base images/upstream package contents changed during the cold rebuild. These
sizes are observed results, not savings attributable solely to the UI changes;
the backend image grew. No CLI functionality was removed for size reduction.

Read-only `du` inventory during the campaign: Git cache 540,852 KiB; environment
workspaces 286,052 KiB; conversation workspaces 1,645,112 KiB; materialized analysis
context 4 KiB; uploads 724 KiB; all native session states 2,066,856 KiB. These include
pre-existing personal histories and are not per-conversation allocation estimates.
No historical native state was deleted merely to improve measurements.

## Deployment and remaining qualification

The final source tree passed the full backend suite and ten browser checks. The
local installation was redeployed, including the final frontend build. Additive
migration 0054 is applied; a verified PostgreSQL custom-format backup was retained
before deployment. Backend/database health checks passed and no active or queued
AI job remained after the load campaign. All 35 load-test conversations were
archived with their histories preserved. The temporary browser-test server and
disposable test database were stopped; the real installation and Caddy were kept.

Five or ten distinct real publication accounts are not available. Controlled HTTP
account isolation is not a substitute for real GLPI/GitLab/Jira/GitHub approval
and destination checks. No new external issue is created by the load probe.
External ticket modification remains deferred by explicit user choice; existing
resumption/reconciliation is the scope of scenario E.

Native deep-analysis concurrency/peak memory and multi-hour native endurance were
not replayed in this campaign. PostgreSQL role/scheduler fixtures and real Linux
isolation checks cover their boundaries, but do not replace provider-backed
three-role load testing. No p95/p99 service guarantee is inferred from these small
samples. Legacy unlabelled random role homes cannot always be safely attributed
to a cycle; unmatched historical homes remain until explicit installation purge.

Use the [operations guide](local-administration.md) for repeatable commands and purge limits.
