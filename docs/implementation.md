# Architecture and implementation notes

This document describes runtime behavior, operations and deterministic runtime checks.
Start with the [README](../README.md) for installation and usage,
[CONTRIBUTING.md](../CONTRIBUTING.md) for local development, and
[SECURITY.md](../SECURITY.md) for deployment access controls.

## Services and runtime

| Service | Purpose |
|---|---|
| frontend | Next.js / React / TypeScript, shadcn/ui components and Tailwind tokens |
| backend | Django / Django Ninja, configuration and business API |
| worker | Persistent PostgreSQL queue, synchronization and analyses |
| database | Application data, separate from analyzed business databases |
| agent-runtime | Codex CLI / Claude Code, isolated on Linux with Bubblewrap |

One Git mirror per remote supplies detached worktrees. Named sources use a stable
provider/instance/remote identifier, independent of account and branch. Mirror locks
serialize access across configurations. Environment worktrees are separated by SHA
generation and branch selection; legacy worktree paths remain compatible. Request
worktrees are separate. Launching a request freezes its SHAs and database selection;
retained commit refs preserve its baseline across later fetches and force-pushes.

An agent receives only its read-only request workspace, attachments and Git cache, plus its own writable session directory. It cannot access application data, GitHub credentials, PostgreSQL credentials or other requests. AI credentials are persisted separately. The runtime needs `SYS_ADMIN` and a compatible seccomp policy to create namespaces; the agent then drops all capabilities. The service uses `init: true` to reap orphaned Bubblewrap children and prevent process exhaustion. Isolation failure stops execution.

Bubblewrap provides the effective sandbox. Codex's internal sandbox is disabled inside that isolation to avoid conflicting namespaces. Linux still mounts sources, cache and attachments read-only. The default Codex model is GPT-6-Luna, configurable through `CODEX_MODEL`. Understanding uses low reasoning effort and technical analysis medium effort. These settings remain internal; users simply connect their ChatGPT account.

Compose networks separate the runtime from the frontend, backend and application database. The worker reaches it through an internal control network. An authenticated relay lets the backend manage connections without joining the runtime network. Internal keys are generated automatically and stored in protected volumes. The agent can reach its AI provider and, when configured, the business database through filtered temporary access. Preserve these boundaries when adapting deployment.

The optional business database is accessed through a request-scoped temporary capability, PostgreSQL parser, function allowlist and read-only transaction. Owner, superuser, write-enabled and object-creation roles are rejected. Responses are limited to 200 rows and queries to five seconds. Credentials never enter prompts. A database baseline identifies the connection; it is not a data snapshot.

Allowed attachments are PNG/JPEG/GIF/WebP, PDF, DOCX, TXT, Markdown, CSV, JSON and LOG, up to 25 MB each and 20 files per request. Random identifiers isolate files in request-specific directories. Their contents are not executed.

Each analysis has a separate supervisor: the full job stops after 295 seconds, orchestration is bounded to 285 seconds and agent calls use the remaining budget. Errors and interruptions appear in the request and job log. Worker failures are detected on restart.

The pipeline selects useful roles: Requirement Analyst, Code Analyst and Ticket / Goal Writer for simple requests; Attachment Analyst for files and Reviewer for standard, complex or database-backed requests. Code/Writer or Reviewer/Writer may share a structured terminal invocation. Only one additional targeted verification is allowed, with at most ten invocations and two provider attempts per job execution, including format repair. Exchanges are typed and persisted; agents cannot change application workflow. Internal skills cover code navigation, Git history, impacts, minimal changes, attachments, read-only PostgreSQL and Tryton/Coog conventions. Artifacts contain conclusions, never a chain of thought.

The default single worker runs jobs sequentially. Different browsers can submit different requests to the persistent queue; concurrent operations on the same request are guarded. Shared visibility does not provide per-user authentication or privacy.

Git network operations have a ten-minute timeout each. Full synchronization has a separate twenty-minute limit; an initial large download can take longer than an analysis.

## Dashboard and ticket publication

The desktop shell has a persistent instance sidebar, central route content and an
independent task panel. Mobile layouts keep navigation and connection indicators
available and put the queue in an accessible drawer. The queue endpoint reads
persisted jobs; it does not claim work or create a second AI scheduler. Queued rows
follow creation time and ID, active rows remain visible and terminal history is
bounded. Publication attempts appear as short operations with their own persisted
delivery state. Card transitions respect reduced-motion settings.

`TicketConnector` stores encrypted configuration and an explicit destination
allowlist. `PublishedTicket` records the exact immutable source version, edited
payload, operation reference and delivery state. A conditional destination
constraint prevents concurrent or repeated successful/uncertain publication;
definitively rejected attempts can be corrected without rewriting their snapshots.
Destination identities are hashed to keep PostgreSQL unique indexes bounded.

Publication uses ordinary backend HTTP adapters, without any analysis agent or
repository write capability. Reads and writes have bounded timeouts and response
sizes; credentials stay on the configured origin and redirects are not followed.
Uncertain responses remain uncertain until the external reference is found. No
write is triggered by page loading, AI output or external template text.

See [ticket publication](ticketing.md) for platform compatibility, templates,
mandatory fields, faithful previews and recovery behavior.

## Operations

```sh
docker compose ps
docker compose logs --tail=100 backend worker agent-runtime
docker compose down
```

`down` preserves volumes. Back up the application database, `app-data` (including its encryption key), uploads, AI sessions and credentials together. Keep mirrors and worktrees for historical baselines. Do not use `down -v` on an instance you need to preserve.

Volume names use the `spechelper` prefix. Automatic source modification, PR creation, business writes and multi-tenant management are not implemented. Infrastructure controls access to the entire instance.

## Runtime checks

These commands exercise Linux isolation and the complete workflow without an AI account.
Run them from the repository root.

```sh
docker compose run --rm --no-deps agent-runtime python -m runtime.smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.workflow_smoke
docker compose run --rm --no-deps agent-runtime python -m runtime.workflow_smoke claude
docker compose run --build --rm --no-deps agent-runtime python -m runtime.process_smoke
```

The workflow test uses a deterministic terminal agent that reads a real worktree and verifies clarification, session resumption and SHA exports. Its duration measures application behavior, not real AI speed. `process_smoke` performs 300 isolation checks and verifies that zombies do not accumulate. Keep the Compose service's init process and process limit; manual Docker invocations need `--init --pids-limit 256`.

To also check isolated agent → temporary capability → PostgreSQL access, use an **already available disposable** database reachable from the runtime's `agent-egress` network:

```sh
docker compose run --rm --no-deps \
  -e 'SPECHELPER_SMOKE_POSTGRES_DSN=host=test-server dbname=postgres user=postgres password=test-password' \
  agent-runtime python -m runtime.database_smoke codex
```

Replace `codex` with `claude` to exercise the other adapter. This test creates and removes a schema and role; never target a database you need to preserve. It checks reads, rejected writes, password exclusion from prompts and capability expiration.

The [v1.2 audit](acceptance-v1.2.md) distinguishes deterministic checks from
connected-account validation. [v1.1](acceptance-v1.1.md) and
[v1.0](acceptance.md) retain historical evidence. Public reports are anonymized,
dated tests, not connections or latency guarantees supplied with a new installation.
Current language behavior and checks are described in [localization](localization.md).

---

> Public version: session/request identifiers and instance references are anonymized. Original evidence remains local.

> Historical v1.0 implementation notes. Current behavior, migrations and evidence are documented in the [v1.2 audit](acceptance-v1.2.md), [v1.1 audit](acceptance-v1.1.md) and the [README](../README.md).

## Historical v1.0 specification tracking

This document tracks the full scope. A requirement is accepted only after verification. The [detailed audit](acceptance.md) distinguishes every section, thirteen criteria and outstanding evidence.

| Requirement | Expected implementation | Expected evidence |
|---|---|---|
| 1, 6, 28.1 | GitHub connection, organizations, repositories, branches | Controlled GitHub transport API and integration test |
| 5, 28.2, 28.13 | Name/color, shadcn/Tailwind tokens | API persistence and browser checks |
| 7, 19, 28.6 | ChatGPT/Claude, persistent credentials, per-request sessions and resume | Isolated runtime and clarification/resumption scenario |
| 8, 28.4, 28.8–9 | Optional database, read-only role/transactions | Actual PostgreSQL: reject privileged roles and writes |
| 9–12, 28.3 | Multiple environments, shared mirror/worktrees, sync/health check | Real Git with two branches |
| 13, 28.12 | Immutable baseline and workspace | Synchronize after analysis without changing the snapshot |
| 14–15, 28.5 | Business workflow, isolated attachments | Browser and upload/path traversal tests |
| 16–20, 26 | Persistent queue, clarification, analysis and states | Worker tests and browser workflow |
| 17, 27, 28.9 | Read-only sources, secrets outside prompts, no database writes | Isolation tests inside Docker runtime |
| 21, 28.11 | Fast acknowledgment, progress, interruption before 300 s | Timeout test and integration timings |
| 22–23, 28.10 | Complete ticket, Jira copy, Markdown download | Schema, export and browser validation |
| 24–25 | Required stack, Compose/volumes, ten models | Build, migrations, Compose startup |
| 2–4 | Trusted team, no accounts, Admin panel, system | Interface and deployment documentation |

An administrator configures real GitHub/AI accounts. Deterministic tests use controlled transports and a test agent; they do not establish a real model's analysis quality.

### Checks performed on October 20, 2026

- 62 backend tests passed with Django using actual PostgreSQL 17 in a disposable container. `backend/tests/test_admin.py` covers encrypted GitHub credentials, discovery and pagination. `test_git.py` uses real Git, two branches and one mirror; resynchronization preserves request workspace and SHAs. `test_postgres_integration.py` verifies read-only roles/transactions and rejection of superusers, table writes and column writes.
- `test_workflow.py` covers isolated uploads, executable rejection, baselines, answers, session identity, export and 295-second supervision. `test_runtime.py` covers internal authentication, workspace path confinement, explicit session resumption, agent termination and database capability expiration.
- Ten Playwright desktop/mobile scenarios passed: administration, business workflow and connections. They include an 11 MB attachment, clarification, answer, ticket, Jira copy and Markdown download, with no horizontal overflow. AI results are explicit fixtures; no model is called.
- Production Next.js build, TypeScript, Ruff, migrations and Compose validation passed. Frontend, backend, worker and runtime images built.
- `python -m runtime.smoke` with Compose capabilities: reads of sources/Git history/attachments; rejected writes to source, cache and attachment; secrets and other sessions inaccessible; own session writable.
- `python -m runtime.workflow_smoke codex` and `claude`: full API/worker/CLI workflow using a real local repository and Bubblewrap, clarification, same-session resumption and SHA export. Latest acknowledgments: 0.167/0.171 s; deterministic workflows: 0.481/0.497 s. These are not real-model benchmarks.
- Docker network: runtime-to-backend connection on the application network rejected; worker reaches runtime through the control network.
- Installed binaries: Codex CLI 0.163.0 and Claude Code 2.1.116. Without credentials, connection status is DISCONNECTED and quotas UNKNOWN.
- All five Compose services started. Health endpoint: `http://localhost:3000/api/health`. Both desktop/mobile Admin scenarios also passed against the production build and PostgreSQL. Test name/theme restored afterward. Only frontend port 3000 is published on 127.0.0.1.
- Token-free connections: guided GitHub/ChatGPT/Claude dialogs, temporary code or Claude confirmation, progress and cancellation. Six browser scenarios use controlled responses. A disposable Compose deployment started the three real CLIs through the public API, received official authorization links on github.com, auth.openai.com and claude.com, then canceled each attempt.
- Worker control relay is authenticated and restricted to connection/health operations. Internal secrets are generated in protected volumes outside the sandbox. Tests cover the relay, concurrent secret generation and credential renewal without overwriting a newer login.

### External validation limits

The user connected GitHub and ChatGPT. Discovery, a public project and both private projects in the existing environment were synchronized with those accounts. Real analyses with/without attachments produced tickets after clarification and session resumption; sources, sections, exports and timings are checked in the [detailed audit](acceptance.md).

Final post-answer jobs took 45.786 and 73.546 s. First clarification took 23–26 s, exceeding the indicative 15-second ideal. Simple/standard targets and the mandatory five-minute limit are distinct. These results do not guarantee external-provider latency. A reduced-budget real Linux timeout supplemented the 295-second supervisor tests.

Claude remains an alternative. Its official authorization startup and adapter were tested; no analysis using a real Claude account is claimed. The specification requires at least one of the two terminal agents; connected analyses above used Codex.
