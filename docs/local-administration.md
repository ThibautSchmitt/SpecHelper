# Local operations and load qualification

## Retiring an analysis or publication

Use the **…** menu beside a deep-analysis cycle to delete that cycle and its
results. The confirmation does not delete the conversation, another cycle or an
external ticket. Active invocations are cancelled with their existing attempt
identifiers. Cleanup waits for runtime acknowledgement and retries from worker
maintenance if the browser closes. A stopped process cannot commit a late result.

Unreferenced result bodies and generated reports are removed. Small identifiers
and sequence numbers remain reserved. Frozen source snapshots needed by an
existing ticket, transferred document or derived question remain available to
that dependent record, without reappearing as an active analysis. The shared Git
cache and conversation workspace are not cycle-owned and are preserved.

In **Published tickets**, **… → Remove from SpecHelper** removes one local
publication from the history and conversation. No remote DELETE or modification
is performed. Other publications remain. The local destination, original
connection, external reference and idempotency digest are retained to prevent
the removed operation from being sent again; its duplicate publication payload
is cleared. An unresolved write or attachment transfer cannot be hidden through
this action.

Migration `0054_local_analysis_publication_retirement` adds nullable retirement
timestamps and visibility managers. It does not drop tables or historical rows.
Back up PostgreSQL before deployment as described in [installation](installation.md).

## Stop, clean and purge

Run from the installation checkout with Docker available:

```sh
./scripts/cleanup.sh stop --project spechelper --dry-run
./scripts/cleanup.sh stop --project spechelper
./scripts/cleanup.sh clean --project spechelper --dry-run
./scripts/cleanup.sh purge --project spechelper --dry-run
```

- `stop` stops this installation's containers and preserves their data.
- `clean` stops/removes the containers, exclusive Compose networks and exclusive
  labelled build images. Persistent volumes are preserved. Type `CLEAN SPECHELPER`.
- `purge` additionally removes exclusive labelled volumes: application
  PostgreSQL, local Git copies, uploads, reports, credentials, native session
  states and caches stored there. Type `PURGE SPECHELPER`.

After reviewing the dry run and safeguarding any data to retain:

```sh
./scripts/cleanup.sh purge --project spechelper
```

There is no noninteractive confirmation bypass. `--directory /absolute/checkout`
identifies another installation. Project labels and container working-directory
labels must match. A minimal `.spechelper-installation.json` receipt allows later
purge after `clean` has removed the containers; the receipt is removed by purge.
Resources are re-inventoried before deletion. Shared/in-use resources and
unverified ownership are preserved or rejected. No global Docker prune is used.

Host bind mounts, the source checkout, `.env`, host-side backups and pre-existing
host directories are **not** recursively deleted. The inventory displays bind
paths for separate administrative review. Upstream/shared images and external
volumes remain. Docker’s shared BuildKit cache is preserved because its layers
cannot be safely attributed exclusively to one Compose installation. No external ticket, remote Git repository or business database is
deleted. Review residual shared resources after purge; this is intentionally not
a secure erasure of disk blocks, backups or provider-held data.

## Reproducible measurements

The sampler uses finite, sequential `docker stats --no-stream` calls. It never
prints container environment variables or process command arguments:

```sh
mkdir -p .local/load
python3 scripts/evaluation/resource_probe.py --project spechelper \
  --phase idle --samples 20 --interval 3 \
  --api-url http://localhost:3000/api/health --output .local/load/idle.json
docker compose exec -T agent-runtime python < scripts/evaluation/runtime_process_probe.py
```

The process probe reports Linux names, RSS, threads, zombies and cgroup limits.
Docker PIDs include threads; summed RSS double counts shared pages. Sampled peaks
can miss short spikes. Health latency does not measure an AI answer. Collect idle,
native-load and post-load windows on the same hardware, without simultaneous
image builds or unrelated test suites. Do not report gains across unlike windows.

Logical native session state persists on disk; a completed invocation does not
require a resident CLI process. The runtime admits at most two CLI invocations
at once under its existing CPU/RAM/PID and shared sandbox-UID task budget of 128.
The default global scheduler capacity is also two, avoiding worker-process churn
for slots the runtime cannot accept. Existing environment overrides remain explicit.
Excess work returns BUSY to the existing scheduler instead of starting another
process. Account and global scheduling limits still apply; native quotas and
independent role contexts are unchanged.

## Controlled and real load tests

Use a disposable PostgreSQL server and a **distinct** `POSTGRES_DB` for each
simultaneous pytest process. Never point tests at the application database.

```sh
cd backend
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 POSTGRES_DB=spechelper_load \
  POSTGRES_USER=postgres POSTGRES_PASSWORD=fixture-only \
  .venv/bin/pytest -q tests/test_persistent_discussion_postgres.py \
  tests/test_v24_scheduler.py tests/test_publication_load_postgres.py \
  tests/test_local_deletion.py tests/test_publication_query_budget.py
```

The discussion/scheduler tests use real PostgreSQL locks with simulated AI
responses. Publication load tests use real concurrent HTTP and distinct synthetic
account tokens against an in-process GitLab contract fixture. They include lost
creation responses, read-only reconciliation and repeated confirmations; they
do **not** establish provider capacity or validate real GLPI/Jira/GitHub accounts.

For actual native CLI conversations, configure a dedicated local test environment
containing non-sensitive SpecHelper sources. This consumes real provider quota:

Install the frontend's locked Node dependencies and a compatible Chrome/Chromium
browser first; see [development](development.md#frontend-checks). The probe uses
Playwright from `frontend/node_modules` and defaults to the installed `chrome`
channel. `PLAYWRIGHT_CHANNEL` selects another installed compatible channel. It opens
a fresh browser session: a password-protected instance is rejected unless that
session is authenticated. Use a separate loopback-only test installation; do not
disable access controls on the real team instance to run this probe.

```sh
mkdir -p .local/load
node scripts/evaluation/conversation_load.mjs --environment 10 --parallel 5 \
  --rounds 1 --output .local/load/native-5.json --allow-inference
node scripts/evaluation/conversation_load.mjs --environment 10 --parallel 10 \
  --rounds 1 --output .local/load/native-10.json --allow-inference
# Five waves on the same ten conversations, scheduled over two hours:
node scripts/evaluation/conversation_load.mjs --environment 10 --parallel 10 \
  --rounds 5 --reuse-conversations --interval-seconds 1800 \
  --output .local/load/native-endurance.json --allow-inference
```

Replace `10` with the actual dedicated environment ID. Run resource sampling in a
second terminal during each batch and again after it. Reports retain test
conversation identifiers and timings without response bodies or authentication
headers. The probe never publishes tickets or changes connections/roles. A
timed-out or transport-interrupted batch may leave its recorded operations active:
inspect them and cancel them normally before another test or redeployment.

`--base` defaults to `http://localhost:3000` and accepts only `localhost` or
`127.0.0.1`. `--parallel` accepts 5 or 10; `--rounds` accepts 1–20.
`--timeout-seconds` defaults to 1200 and accepts 30–3600 seconds per batch.
`--reuse-conversations` resumes the same native threads on subsequent rounds;
without it, each round creates fresh conversations. `--interval-seconds` accepts
0–3600 and requires reuse; it schedules wave starts, waiting for completion before
the next wave. A two-hour schedule is not proof of two hours of successful work:
check completion counts, quota waits and recorded session identifiers.
`--environment`, `--output` and `--allow-inference` are required. A batch timeout
does not cancel its outstanding jobs; test conversations and histories remain
available for inspection and normal archive/cancel actions.

Repeat batches before interpreting percentiles. For 5–10 observations, retain raw
latencies and error causes; p95/p99 are not service guarantees. Use explicitly
approved provider sandboxes for real publication tests. Updating an existing
external ticket remains deferred; test existing draft resumption and uncertain
creation reconciliation instead.

Release qualification requires no mixed contexts/accounts, duplicate writes,
corrupted drafts, persistent orphan processes or forgotten jobs. Derive numerical
CPU/RAM/latency thresholds from the target hardware and its baseline. Current
evidence and unverified cases are recorded in the [qualification report](stabilization-final.md)
and its [8 November follow-up](stabilization-follow-up.md).
