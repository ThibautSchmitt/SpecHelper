# Operations

Start with the [README](../README.md). [SECURITY](../SECURITY.md) owns access and TLS.

## Installation settings

Set `POSTGRES_PASSWORD` in `.env` before first startup. Keep the default loopback
bind for local use. `DJANGO_SECRET_KEY` and `RUNTIME_TOKEN` may remain blank:
protected persistent storage generates them. Preserve their storage and encryption
key across restarts; never replace keys independently of encrypted data.

For another local installation, use a separate directory and set a unique
`COMPOSE_PROJECT_NAME`, unused `PORT` and matching localhost `TRUSTED_ORIGINS`
in its `.env`. Defaults serve port 3000. Compose must support the `!reset` merge tag
used by `prepare-storage`; incompatible older versions fail configuration. Linux
namespace support is required even with Docker Desktop.

## Concurrent conversations and analyses

The current worker is a supervisor: each admitted invocation starts a separate
`manage.py process_job` subprocess, and the supervisor resumes queue admission
without waiting for that subprocess to finish. One `worker` container therefore
supports overlapping jobs; counting worker containers does not measure active
analysis capacity. The two Gunicorn workers serve HTTP requests independently.

PostgreSQL serializes short admission transactions and claims queued jobs with
row locks. It does not hold the global admission lock over inference. One
conversation has one active operation, while different conversations retain
separate state, frozen resources and native sessions. Deep roles remain sequential
within each analysis. Quota/resource waiting yields admission to another runnable
job; it does not reserve future roles.

AI execution slots are shared per detected identity/account group. A discussion
keeps its own pinned connection and native session, while other conversations may
use that account simultaneously. Adding connection aliases does not multiply the
account's slot budget or quotas. Only the ending invocation releases its slot;
cancelled or interrupted work keeps it until its exact runtime stop is acknowledged.

Deployment settings in `.env` (passed to backend and worker):

| Setting | Default | Scope |
| --- | --- | --- |
| `SPECHELPER_AI_ACCOUNT_CONCURRENCY` | 4 | Active invocations across all aliases of one account, bounded to 1–32 |
| `SPECHELPER_AI_CONCURRENCY` | 8 | Active AI invocations across the instance, bounded to 1–64 |

Discussion turns, deep-analysis checkpoints and library assistants share these
budgets. Values of `1` retain serialized execution. For ten concurrent discussions
using one account, both limits must be at least ten, for example:

```dotenv
SPECHELPER_AI_ACCOUNT_CONCURRENCY=10
SPECHELPER_AI_CONCURRENCY=10
```

Apply deployment configuration to both backend and worker. These are application
ceilings, not a claim that a subscription accepts that many simultaneous calls.
Observed provider busy/backoff, authentication failure, model-specific exhaustion
and shared quota windows remain authoritative. Waiting jobs remain queued; no
provider/model/session switch is introduced. CLI updates wait until every active
or not-yet-stopped slot has drained.

The default single runtime shares two CPUs, 2 GiB of memory and a 256-process limit
across invocations. Keep those resources in mind before increasing concurrency;
worker replicas alone do not add provider capacity or runtime memory.
`SPECHELPER_CONCURRENCY` is a different setting: it limits concurrent HTTP requests
per access actor, not background AI executions.

Validation on 2026-10-30 uses real PostgreSQL locks and controlled provider calls:
account aliases share their atomic cap, a separate instance cap spans accounts,
and independent discussions can overlap on one account with distinct sessions,
workspaces and human context. The discussion test includes ten simultaneous calls
when configured for ten. Runtime sandbox probes separately validate real Linux
process overlap, read-only sources and exact-attempt cancellation without calling
a live model. Subscription throughput is not established by these fixtures.
Final checks for this change: 1,376 backend tests passed with 26 environment-dependent
skips; 20 PostgreSQL concurrency tests passed. Ruff, Django system/migration checks,
TypeScript and the production frontend build passed. The deployed worker reports
the default 4 account slots / 8 instance slots. A live-provider smoke was attempted,
but both configured connections reported exhausted quotas before any synthetic
conversation or inference was created.
Browser-owner conversation isolation does not supply individual human accounts;
see [ownership and historical compatibility](analysis.md#ownership-and-historical-compatibility).

## Upgrade and recovery

Review [CHANGELOG](../CHANGELOG.md), coordinate backups and wait for active work.
Rehearse migrations on a protected restored copy and verify historical rows,
artifacts and credential decryptability before upgrading the shared instance.
`docker compose up --build -d` builds images and starts automatic migrations;
source publication alone does not upgrade a running instance. Never run destructive
database tests or browser fixtures against a team deployment.

Retry interrupted work through its saved checkpoint. Never force-clear an account
lease while the old process may still be active; see the
[execution contract](analysis.md#execution-contract).

## Daily operations

```sh
docker compose ps
docker compose logs --tail=100 backend worker agent-runtime
docker compose down
```

`down` preserves volumes. Coordinate backups of PostgreSQL, `app-data`, uploads,
AI sessions, context documents, encrypted AI credentials and the matching
`runtime-control-secrets` volume. Store encryption keys separately from database
exports with restricted access. CLI encryption derives from the control key;
restoring credentials without the matching key requires reconnecting the accounts.
Keep mirrors/worktrees for historical baselines. Do not use `down -v` on an
instance you need to preserve.

Volume names use the Compose project prefix (`spechelper` by default). Automatic source modification, PR creation,
business writes and multi-tenant management are not implemented. Shared-password
access protection applies to the whole team; remote TLS/proxy requirements are
documented in [SECURITY.md](../SECURITY.md).

## Runtime checks

These commands exercise current Linux boundaries with synthetic data and no AI account.
Run from the repository root in a disposable Compose project:

```sh
docker compose run --rm --no-deps agent-runtime python -m runtime.v19_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.v24_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.v25_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.v27_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.v27_oauth_smoke
```

These cover containment, parallel context/skill/Git isolation, cancellation and the
public-reference broker. Controlled terminal/HTTP fixtures do not measure real AI
quality. Older adapter/workflow and process-regression commands remain available
below; they exercise historical contracts, not complete current-provider acceptance.

The Antigravity probe uses the pinned real CLI with synthetic Gemini responses and
credentials. It invokes no live model. CLI upgrades require updating the explicit
release manifest/checksums and passing native metadata, schema, permission, tool,
isolation and cancellation checks again; do not use a rolling installer or silently
auto-update the running image. See [Antigravity](antigravity.md).

```sh
docker compose run --rm --no-deps agent-runtime python -m runtime.smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.workflow_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.workflow_smoke claude
docker compose run --build --rm --no-deps agent-runtime python -m runtime.process_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.v16_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.v17_smoke
docker compose run --rm --no-deps -e SPECHELPER_SMOKE_STACK=typescript \
  agent-runtime python -m runtime.v17_smoke
docker compose run --rm --no-deps -e SPECHELPER_SMOKE_STACK=typescript \
  -e SPECHELPER_SMOKE_CONFRONTATION=1 -e SPECHELPER_SMOKE_DUAL_PROVIDER=1 \
  agent-runtime python -m runtime.workflow_smoke
```

The workflow test uses a deterministic terminal agent that reads a real worktree and verifies clarification, session resumption and SHA exports. Its duration measures application behavior, not real AI speed. `process_smoke` performs 300 isolation checks and verifies that zombies do not accumulate. Keep the Compose service's init process and process limit; manual Docker invocations need `--init --pids-limit 256`.

Current jobs have no total business deadline. Technical limits still exist: the
runtime accepts invocation timeouts up to 600 seconds, current orchestration uses
its tool timeout, and the worker supervisor has a 900-second stuck-invocation guard.
SQL and Web transfers have their own smaller bounds. Historical contracts keep
their original limits; their reports must not be read as current product deadlines.

To also check isolated agent → temporary capability → PostgreSQL access, use an **already available disposable** database reachable from the runtime's `agent-egress` network:

```sh
docker compose run --rm --no-deps \
  -e 'SPECHELPER_SMOKE_POSTGRES_DSN=host=test-server dbname=postgres user=postgres password=test-password' \
  agent-runtime python -m runtime.database_smoke codex
```

Replace `codex` with `claude` to exercise the other adapter. This test creates and removes a schema and role; never target a database you need to preserve. It checks reads, rejected writes, password exclusion from prompts and capability expiration.


## Synchronization and provider incidents

Git clone/fetch each has a ten-minute technical timeout; full synchronization has
a separate twenty-minute guard. An initial download may be slow. Check environment
synchronization history for stored operations/redacted errors. Successful sync is
hidden from the task panel but retained in diagnostics.

Known exhausted/busy accounts leave work waiting. Metadata refresh does not prove
inference capacity or clear exhaustion; [configuration](configuration.md) owns quota
observations. Preserve runtime init/PID settings: missing init previously caused
orphan accumulation and blocked work; the archived v1.2 report records that incident.

## Source publication

Publish reviewed sources, tests, locks, notices and configuration examples. Exclude
`.env`, private specifications, `.local`, backups, uploads, results, credentials,
provider sessions, dependencies, caches and generated reports. Separate synthetic
fixtures from real data. Review staged files, secret scans, notices and whitespace.
Use a Conventional Commit with Context, Changes and Scope in its body. Report push,
deployment and validation separately. GitHub Actions checks disposable services;
it neither deploys nor needs AI accounts. Inspect actual CI results before claiming
they passed. [Security validation](security-testing.md) owns scanner gates/exceptions.

## Installation observation

On 2026-10-24 a clean source copy ran the README copy/configure/start sequence
with a new Compose project, fresh volumes, port 3016 and matching trusted origins
to avoid the existing instance. All five long-running services started;
`prepare-storage` exited successfully, database/backend health passed, and
`/api/health` returned `{"status":"ok"}`. The worker reached the runtime with
authentication; its seeded assistants were disconnected, with zero requests and
environments. All core migrations through 0033 applied. Requests, Questions and
Settings opened in Chrome with HTTP 200 and no page errors; the documented
v2.5 Linux smoke also passed on this clean project's image. Build layers were
reused: this proves clean application/data startup, not uncached registry downloads
or connected AI analysis. The disposable project was stopped after validation.
