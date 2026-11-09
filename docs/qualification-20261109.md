# Qualification — 9 November 2026

This follow-up records actual local provider execution. Cancellation, session
resumption and four real GitLab/GLPI publication scenarios completed. Extended
endurance reached 64/70 answers; six final operations were quota-blocked and
cancelled normally, so the entire seven-wave protocol is not a passing test.
Deep-analysis execution and historical preservation passed, with a remaining
Antigravity tool-error limitation: none of these three cycles is a fully verified
result. Real GitHub/Jira qualification and external ticket editing remain deferred.

## Installation and controls

The Docker VM exposes eight CPUs and 8,240,336,896 bytes of RAM (about 7.67 GiB),
using Engine 24.0.5. The application retained the deployed backend/worker image
`sha256:c6807152979cf790e82b907b73b9d77b592d14fd0207a2892505a9a48d1d3400`.
No image build, image export or destructive purge ran during qualification.

Sources in the dedicated SpecHelper environment were synchronized before inference
and remained frozen at `9bdc3d0c35415f78d602ac50cc32e21d67f0880c` throughout the tests.
Both existing AI connections authorized all three roles on this date. The bench
changed no roles, quotas, permissions or concurrency limits. Analyst and Validator
used ChatGPT/Codex; Counter-analyst used Antigravity. Two native slots, the runtime's
two-CPU/2-GiB/256-task limits and the 128-task sandbox budget remained unchanged.

The unlicensed local Jira **application** was stopped before the test to release
test-lab memory; its data and database were retained. GitLab and GLPI test services
remained available. Application totals below exclude these lab services and other
projects, so they are not total VM-memory measurements. No GitHub/Jira publication
or change to an existing external ticket was attempted.

## Native roles, cancellation and restart

Two independent deep cycles submitted at 05:28 UTC completed their required
checkpoints in 441.50 and 436.32 seconds. Their narrow subjects were the scheduler
default/bounds and the strict human-confirmation validator. Sources cite actual
files and the frozen commit. All three roles finished; the two results remained
`PARTIAL` because Antigravity's comparison checkpoint reported an unresolved tool
error. A successful later role did not erase that limitation.

A second cycle in one of those conversations completed in 489.58 seconds. It
preserved the first cycle's timestamps, frozen context and role reports, and used
new contexts. The same Antigravity comparison limitation recurred. Across all
three cycles, a database check found 18 completed step executions, 18 distinct
execution contexts and 18 distinct nonempty native session identifiers. No draft
or publication was created by those analyses. The retained diagnostics do not
establish the precise cause of the provider tool error; this remains unresolved.

Queued cancellation and cancellation of an actually running invocation both
succeeded through normal APIs. After active cancellation, the conversation returned
to discussion and no late assistant reply appeared during the 15-second check.
The runtime returned to its server/init/probe processes without a resident CLI.

A separate conversation completed inference before and after a controlled restart
of the worker and native runtime at 05:39–05:40 UTC. It recalled the test marker and
retained exactly the same context and native Codex session identifier. This is an
actual resumed inference, not just persistence of database metadata.

## Sustained native conversations

The same ten conversations received seven bursts scheduled 30 minutes apart.
The initial five-wave window ended at 2026-11-09T07:44:08.860Z; the complete
extended observation lasted 3.74 hours, from
2026-11-09T05:42:36.982Z to 2026-11-09T09:26:58.609Z. Six waves completed in full. The last
wave completed four answers before ChatGPT was classified `QUOTA_EXHAUSTED`,
leaving six operations queued. Metadata confirmed 100% use of the short window,
a reset at 10:28:56 UTC, and 50% remaining weekly quota. The six unstarted test
jobs were cancelled through normal APIs; there are no forgotten queued test jobs.
The final count is 64 answers, six quota-related cancellations, zero missing
markers and zero foreign markers among completed answers. Each conversation
retained one context and one native session across its six or seven completed
answers; the ten conversations had distinct identifiers. This is not a 70/70 pass.

The worker correction below required one idle-time recreation at 06:36:57 UTC.
The initial window is therefore not claimed as uninterrupted operation. Two extra
waves extended observation to more than two hours after correction: the first
post-fix wave to the final quota-stop record spans
2.74 hours. The last ten-conversation burst is
incomplete; this does not qualify two hours of fully completed post-fix bursts.
The follow-up deep cycle ran
between bursts and is measured separately. No ticket or deep analysis was
implicitly generated by the conversation questions.

| Wave | Complete | Response min / median / max, seconds | Maximum queue, seconds |
| --- | --- | --- | --- |
| 1 | 10/10 | 26.52/87.72/148.79 | 120.61 |
| 2 | 10/10 | 17.15/51.30/85.20 | 70.06 |
| 3 | 10/10 | 18.03/54.75/98.97 | 79.27 |
| 4 | 10/10 | 18.46/53.66/88.95 | 71.57 |
| 5 | 10/10 | 17.91/54.71/90.94 | 73.86 |
| 6 | 10/10 | 17.43/58.02/94.29 | 76.17 |
| 7 | 4/10 | 18.59/29.74/41.03 | 23.71 |

Response durations include the existing two-slot queue. The latency/queue columns
describe completed answers only. The six final
unstarted operations waited about 44 minutes on quota before cancellation; their
wait is not represented by the last row's completed-answer maximum.
These are short questions about non-sensitive SpecHelper sources, with idle
periods between bursts. They
do not establish ten simultaneous native executions, continuous maximum load,
large-document capacity or p95/p99 service guarantees.

## Measured worker correction and resources

At 06:35 UTC the worker contained 100 unreaped Git zombies parented to PID 1.
The Python worker was PID 1 and did not reap orphaned helper children. Compose now
sets `init: true` for the worker, as already done for the native runtime. Only the
idle worker was recreated, with the same image; no application migration or new
dependency was required. Raising worker or sandbox PID limits was unnecessary.

| Observed idle worker, including the probe | Before correction | Immediately after |
| --- | --- | --- |
| Unreaped Git zombies | 100 | 0 |
| Cgroup tasks, including threads | 104 | 5 |

After correction, 204 valid worker process snapshots were collected.
3 snapshots captured transient zombie states
(maximum 1 at once); no zombie PID persisted into
the next roughly 50-second snapshot. The final snapshot contains zero zombies.
One denied startup of the worker-monitor client was a local sandbox restriction;
that failed observation is excluded from these valid Docker snapshots.

Six application services were sampled sequentially approximately every 18 seconds.
CPU percentages below are relative to **one core**, not the eight-CPU VM total.
Memory is Docker's reported working set, not summed RSS or a secure leak bound.

| Window | Samples | RAM median / sampled peak, MiB | CPU mean / sampled peak, % of one core | Health median / max, ms |
| --- | --- | --- | --- | --- |
| Between-wave reference, 06:00–06:10 | 34 | 679.17 / 784.94 | 38.85 / 141.09 | 9.29 / 11.73 |
| Two concurrent deep cycles | 26 | 1301.70 / 1465.93 | 62.25 / 149.56 | 10.22 / 41.59 |
| Between waves after correction, 07:00–07:10 | 34 | 777.08 / 933.38 | 41.73 / 251.75 | 9.77 / 11.91 |
| Seven native question bursts | 35 | 1005.75 / 1119.66 | 69.09 / 172.57 | 10.36 / 53.84 |
| Follow-up deep cycle | 27 | 1000.27 / 1223.56 | 47.56 / 134.74 | 9.85 / 13.11 |
| Final cooldown | 6 | 901.86 / 996.41 | 64.92 / 136.80 | 9.35 / 10.28 |

Across 809 application samples, there were
0 sampler/health errors. Sampled runtime
zombies, runtime cgroup OOM/PID-limit hits and worker cgroup OOM/PID-limit hits were
zero. The minimum observed Docker-filesystem free space was
2.11 GiB. These are sampled observations;
brief spikes can be missed. The measurements do not diagnose the earlier daemon
stall or establish unlimited uptime.

Warm caches affect the RAM comparison. At 07:40 UTC, cgroup counters distinguished
about 80 MiB anonymous memory / 199 MiB file cache in the idle runtime, and
44 MiB anonymous memory / 140 MiB file cache in CLI maintenance. The measured
correction concerns process reclamation; the different resource windows are not
presented as a controlled CPU/RAM reduction experiment. No resident native CLI
was needed to preserve the idle conversation sessions.

## Four confirmed external publications

The user explicitly approved four neutral tickets, two per configured test
connection: GitLab project `test/test` and GLPI `Root entity`. Every draft selected
one small Markdown file and excluded a second available file. All four real
creations and selected transfers succeeded:

| Platform | Scenario | External reference | Actual create attempts | Files transferred | Bench duration, seconds |
| --- | --- | --- | --- | --- | --- |
| GITLAB | double_confirmation | 4 | 1 | 1 | 4.37 |
| GITLAB | lost_response | 3 | 1 | 1 | 6.64 |
| GLPI | double_confirmation | 4 | 1 | 1 | 1.18 |
| GLPI | lost_response | 5 | 1 | 1 | 3.57 |

Concurrent double confirmations returned one publication. In each lost-response
case, the bench dropped the real provider's accepted creation result before local
success recording; the existing uncertain operation reconciled to `PUBLISHED`
without a second create. This exercises real APIs with controlled SDK-response
loss, not a dropped network packet. The bench blocks an attempted second create
and fails that case; zero duplicates alone would not be sufficient evidence.

Separate-process resumption of all four operation keys made zero new creates and
did not retransmit files. Each confirmed publication retained one conversation
event and released its active draft. Read-only provider checks confirmed one
selected attachment, no excluded attachment link and a creator matching the
authenticated connection in all four cases. This covers two configured accounts,
not ten accounts or an identity-control system for individual users.
The remote titles and project/entity identifiers also matched the reviewed drafts.

Browser checks verified all four direct external links, HTTP 200, a new-tab target,
visibility in Published tickets and exactly one conversation event after reload.
The 18 owned test conversations were then archived without losing their messages,
three analysis cycles or four publications. External tickets remain intact.

The [publication bench](publication-qualification.md) supports later explicitly
approved GitHub/Jira qualification. GitHub's supported issue API has no such file
upload support; its plan must select no attachments. Jira requires an authorized
Cloud REST v3 test project. Neither platform is qualified by these GitLab/GLPI
results. Generated `goal.md`/report contents were not part of this neutral-file test.

## Git discovery and Antigravity update follow-up — 9 November 2026

Commit `c9668353b5f3a622b69632402169af9be2bf22ad` passed
[Checks 42600860398](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42600860398)
and [Security campaign 42600860292](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42600860292).
CI recorded **1,755 passing backend tests** with one existing deprecation warning
and **260 passing browser cases per viewport** (520 total). Source, all three
image gates and DAST passed. A separate local backend run passed 1,716 tests and
skipped 39 cases. Skipped cases are not coverage; PostgreSQL-specific coverage
comes from CI's disposable PostgreSQL setup.

The discovery regressions verify a matching repository beyond 600 remote entries,
bounded continuation through empty pages, namespace filtering and distinct branch
and tag selections. Local Git operations verify annotated-tag resolution and
preservation of an earlier commit when a tag moves. Remote discovery responses
are fixtures. After redeployment, a separate read-only check on the configured
GitHub source found the selected repository by its whitespace-padded path and
retrieved four branches and one tag with the expected reference types. No
environment selection or source content was modified by this check. It is not a
real large-account latency or throughput benchmark.

Antigravity's 1.5.3 update had previously rolled back because the adapter rejected
the release line. After checking the actual executable's version and required
options, the normal maintenance workflow activated 1.5.3 and completed its model
catalogue verification. A real two-turn native smoke test completed both turns in
the same conversation context and native session between 10:17:17 and 10:18:48 UTC.
Its neutral prompts required no tools, deep analysis or ticket publication. The
test conversation was archived with its evidence retained.

This qualifies the update and two-turn discussion resumption only. The earlier
Antigravity comparison-checkpoint tool error was not retested by these prompts
and remains an explicit limitation of the deep-analysis qualification above.
GitHub/Jira publication and larger multi-account/endurance limits are unchanged.
Private native evidence remains in `.local/antigravity-153-smoke.json`; the
read-only deployment check is reproducible with the local helper
`.local/git-search-deployment-check.mjs`. Neither private helper is distributed
as a public test command. Public regression commands are in the
[development guide](development.md#git-discovery-and-cli-update-regressions).

## Code checks and reproducibility

The six new publication-plan/write-fence tests passed locally, as did four real
Compose interpolation/merge tests. CI at `5857cef71d1b2f903a7b6ccc274b3d32c484c77d`
passed [Checks 42575842474](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42575842474)
and [Security campaign 42575842495](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42575842495).
The backend campaign contains 1,745 passing tests; both browser viewport suites
passed all 256 cases each (512 in total). An earlier desktop run exposed
an asynchronous test assertion before the Git-connection POST had arrived; the
assertion now polls for the same exact payload. Twenty local repetitions across
both languages and viewports passed after this correction. No product UI or
provider safety check was weakened.

Reproduce the burst protocol with the existing
[native load command](local-administration.md#controlled-and-real-load-tests),
using `--parallel 10 --rounds 7 --reuse-conversations --interval-seconds 1800` on a
dedicated environment. Run the resource sampler alongside it, and run the Linux
process probe in **both** worker and runtime containers. A clean deployment must
already include the corrected worker init configuration. Use the separately
confirmed publication plan for provider tests; never generate new operation keys
to recover an uncertain publication.

Raw local evidence is retained in `.local/qualification-20261109/`: native
conversation operations/session metadata, role reports, cancellation/resumption,
resource/process samples, publication plans/results and archive checks. It is
excluded from the public mirror. No credentials, private response bodies or
connector secrets were added to the public report. Report generated at 2026-11-09T18:29:44.112240+09:00.
