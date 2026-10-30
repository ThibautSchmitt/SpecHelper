# Installation and operations

## Prerequisites

Use Docker Engine on Linux or Docker Desktop on macOS/Windows, with Docker Compose
supporting the `!reset` merge tag. The runtime needs working Linux mount, PID and
network namespaces, Bubblewrap and seccomp support inside Docker. A restricted host
that cannot establish these boundaries cannot execute agents.

Building downloads pinned packages and CLI releases from upstream. You also need
an eligible AI account and access to a repository for actual analysis. Docker runs
the application PostgreSQL database; a separate business database is optional.

## Configure and start

From the repository root:

```sh
cp .env.example .env
```

Set `POSTGRES_PASSWORD` to a private value before first startup. Preserve `.env`
outside Git. The default bind is `127.0.0.1`, with the frontend on port 3000.
Blank `DJANGO_SECRET_KEY` and `RUNTIME_TOKEN` use generated persistent secrets;
do not replace them independently of their data.

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Storage preparation initializes ownership. The backend applies migrations before
serving requests. The worker, isolated runtime and CLI maintenance service start
with their required networks and volumes. No separate account-creation wizard is
required. Open <http://localhost:3000> and follow [Configuration](configuration.md).

Verify the frontend, API health and startup logs:

```sh
curl --fail http://localhost:3000/api/health
docker compose logs --tail=100 backend worker agent-runtime
```

For an authenticated remote instance, check health through an authenticated session
or the backend's internal health check. Successful startup establishes application
availability, not provider entitlement, model quality or ticket-write permissions.

## Ports and remote access

If port 3000 is occupied, set `PORT` and matching `TRUSTED_ORIGINS` in `.env`, then
recreate the services. For example, port 3016 needs `http://localhost:3016` and/or
`http://127.0.0.1:3016` as the origins actually used by the browser.
For a separate installation, also set a unique `COMPOSE_PROJECT_NAME` so its volumes
and networks are distinct.

Keep the loopback bind for local use. Remote deployment requires the shared access
password, HTTPS and appropriate host/origin settings described in [SECURITY.md](../SECURITY.md).
Do not publish backend, database, worker-control or runtime ports to users.

## Concurrent work

Set these deployment variables before recreating backend and worker:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `SPECHELPER_AI_ACCOUNT_CONCURRENCY` | 4 | Active AI invocations shared by aliases of one detected account; range 1–32 |
| `SPECHELPER_AI_CONCURRENCY` | 8 | Active AI invocations across the instance; range 1–64 |

Discussion turns, deep-analysis checkpoints and library assistants share the slots.
One conversation still has one active operation. Set both values to at least ten
if you want to allow ten simultaneous discussions on one account. Setting a ceiling
does not establish the provider's actual capacity or increase its quota.
`SPECHELPER_CONCURRENCY` separately limits HTTP requests per access actor; it does
not configure background AI work.

The default agent runtime shares two CPUs, 2 GiB RAM and a 256-process limit.
Increasing slots does not add host resources. See [Architecture](architecture.md#parallel-work-and-cancellation).

## Stop, restart and upgrade

```sh
docker compose stop
docker compose start
```

`docker compose down` also removes containers and networks while preserving named
volumes. Do not use its volume-deletion option on an instance you need to keep.
For an upgrade, stop new work, wait for active invocations and publication to finish,
back up data, then rebuild:

```sh
docker compose up --build -d
```

Automatic migrations update the application database. Rehearse them on a protected
copy when upgrading a team installation. Source commits or pushes alone do not
upgrade running containers. Use the in-application CLI update action for detected
CLI releases; it drains active work before replacement and reports uncertain outcomes.

## Backups and recovery

Back up application PostgreSQL and the matching named volumes:

- `app-data`, uploads, context originals and verified context copies;
- Git mirrors, environment and analysis workspaces needed by retained baselines;
- AI sessions and encrypted credentials;
- runtime control secrets, the Django secret and the matching encryption key.

Volume names use the Compose project prefix. Keep database exports and keys in
separately protected storage. The encryption key normally lives at
`/data/encryption.key`; CLI vault encryption derives from the runtime control key.
Replacing either key independently can make retained credentials unreadable.
Test restores before relying on a backup. Removing a document or analysis from an
active view is not a backup-retention or secure-erasure policy.

Retry interrupted work through the application's saved checkpoint. Do not force-clear
account reservations while an old runtime attempt may still be active. Confirm
uncertain ticket delivery at the external destination before retrying any write.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Compose rejects `!reset` | Install a compatible Docker Compose; do not remove isolation settings to make startup pass. |
| Backend is unhealthy | Inspect migration/startup logs, database readiness and the configured database password. Changing `.env` does not reset an existing PostgreSQL volume's password. |
| Provider configured but analysis waits | Inspect actual connection/model access, account slots, quota windows and their freshness. Authentication or an elapsed reset time alone does not prove recovery. |
| CLI starts but source tools fail | Check namespace/seccomp support, runtime memory/PID limits and logs. Preserve `init: true` so child processes are reaped. |
| Model absent after refresh | Refresh reads the installed CLI catalogue. Check the displayed CLI version and explicit update action; no model list is invented. |
| Session cannot resume | Keep the application history. The UI reports a replacement session rather than silently claiming native continuity. |
| Publication response was lost | Use the existing-publication verification action and inspect the destination; do not blindly submit again. |

Read [Security testing](security-testing.md) for isolated probes and
[Development](development.md) for contributor checks. Never target the team's running
instance with destructive tests or active security scans.
