# SpecHelper

A self-hosted application that turns a business request into a concise ticket and a detailed `goal.md`, based on actual project sources. One installation serves a trusted team with shared GitHub, ChatGPT and/or Claude connections. See the [functional scope](docs/specification.md).

SpecHelper-owned code is released under the [MIT license](LICENSE). Dependencies retain their [licenses and notices](THIRD_PARTY_NOTICES.md), including pglast under the GPL. Built Docker images are not exclusively MIT-licensed. Working PDF briefs, private data and original validation evidence are not distributed.

## Quick start

Install Docker Engine on Linux or Docker Desktop on macOS/Windows, with Compose and Linux namespace support. The agent runtime runs on Linux.

```sh
cp .env.example .env
# Set the local application database password in .env.
docker compose up --build -d
```

Open <http://localhost:3000>. Neither the API nor the runtime exposes a host port. There are no application accounts or private user spaces. For remote access, protect the entire instance, including Admin, with your team's VPN, reverse proxy or SSO. Configure `BIND_ADDRESS`, `TRUSTED_ORIGINS` and `ALLOWED_HOSTS` accordingly and serve the interface over HTTPS.

In **Admin** (labels follow the selected language):

1. Select **Connect with GitHub**, then follow the official browser authorization link and temporary code.
2. Select **Connect with ChatGPT** and/or **Connect with Claude** and follow the official link. For Claude, paste the confirmation code into the connection dialog. This flow requires no personal access token or terminal command. It uses the official GitHub CLI, Codex and Claude Code applications. A compatible provider subscription may be required. Quotas and reset times remain `UNKNOWN` when not officially exposed.
3. Under **Environments**, optionally add a PostgreSQL connection using a host or URL and a dedicated read-only role. **Test connection** checks connectivity, a read and read-only permissions; only these three statuses are displayed. Secrets remain masked.
4. Load projects from GitHub, select their versions and an optional database, and create an environment. Wait for `READY` after synchronization.
5. Edit environments with a preview of changes, or delete one by typing its name. Existing requests retain their references.
6. Under **Instance**, set the team name, optional short label and color. **Application language** selects English or French for the interface and new analyses. French is the default to preserve existing installations. A request's language is frozen at creation, including later discussion and exports; changing the instance language does not rewrite historical artifacts. You can also allow or disable comparison for new requests. Agent and skill configuration remains internal and is not exposed in Admin.

Under **Requests**, select an environment, describe the need and attach useful documents. **Compare multiple analyses** runs two independent analyses followed by synthesis. When two providers are available, each supplies an analysis; one provider is sufficient with two separate sessions. Synthesis has its own context, and exchanges are bounded.

Without comparison, an available assistant is selected automatically. Known exhausted quotas are excluded. Unavailability can trigger a bounded attempt with the other assistant or leave the request waiting for capacity. The application displays this wait without inventing quota information.

Clarification answers resume the request's AI session when its provider remains available. A provider change creates a separate context and never reuses another provider's session ID. Results include a concise ticket for copying to Jira and a detailed, copyable and downloadable `goal.md` with baseline SHAs, relevant files, constraints, acceptance criteria and expected tests. It explicitly asks the implementer to verify sources before modification. **Continue discussion** creates a new immutable result version in the same request; previous versions remain selectable and downloadable. No external Jira ticket is created automatically.

## Architecture and safeguards

| Service | Purpose |
|---|---|
| frontend | Next.js / React / TypeScript, shadcn/ui components and Tailwind tokens |
| backend | Django / Django Ninja, configuration and business API |
| worker | Persistent PostgreSQL queue, synchronization and analyses |
| database | Application data, separate from analyzed business databases |
| agent-runtime | Codex CLI / Claude Code, isolated on Linux with Bubblewrap |

One Git mirror per repository supplies detached worktrees. Each repository/environment has a fixed worktree location; older layouts are normalized at the next synchronization. Environment and request worktrees are separate. Launching a request freezes its SHAs and database selection; later synchronization preserves its context and baseline.

An agent receives only its read-only request workspace, attachments and Git cache, plus its own writable session directory. It cannot access application data, GitHub credentials, PostgreSQL credentials or other requests. AI credentials are persisted separately. The runtime needs `SYS_ADMIN` and a compatible seccomp policy to create namespaces; the agent then drops all capabilities. The service uses `init: true` to reap orphaned Bubblewrap children and prevent process exhaustion. Isolation failure stops execution.

Bubblewrap provides the effective sandbox. Codex's internal sandbox is disabled inside that isolation to avoid conflicting namespaces. Linux still mounts sources, cache and attachments read-only. The default Codex model is GPT-6-Luna, configurable through `CODEX_MODEL`. Understanding uses low reasoning effort and technical analysis medium effort. These settings remain internal; users simply connect their ChatGPT account.

Compose networks separate the runtime from the frontend, backend and application database. The worker reaches it through an internal control network. An authenticated relay lets the backend manage connections without joining the runtime network. Internal keys are generated automatically and stored in protected volumes. The agent can reach its AI provider and, when configured, the business database through filtered temporary access. Preserve these boundaries when adapting deployment.

The optional business database is accessed through a request-scoped temporary capability, PostgreSQL parser, function allowlist and read-only transaction. Owner, superuser, write-enabled and object-creation roles are rejected. Responses are limited to 200 rows and queries to five seconds. Credentials never enter prompts. A database baseline identifies the connection; it is not a data snapshot.

Allowed attachments are PNG/JPEG/GIF/WebP, PDF, DOCX, TXT, Markdown, CSV, JSON and LOG, up to 25 MB each and 20 files per request. Random identifiers isolate files in request-specific directories. Their contents are not executed.

Each analysis has a separate supervisor: the full job stops after 295 seconds, orchestration is bounded to 285 seconds and agent calls use the remaining budget. Errors and interruptions appear in the request and job log. Worker failures are detected on restart.

The pipeline selects useful roles: Requirement Analyst, Code Analyst and Ticket / Goal Writer for simple requests; Attachment Analyst for files and Reviewer for standard, complex or database-backed requests. Code/Writer or Reviewer/Writer may share a structured terminal invocation. Only one additional targeted verification is allowed, with at most ten invocations and two provider attempts per job execution, including format repair. Exchanges are typed and persisted; agents cannot change application workflow. Internal skills cover code navigation, Git history, impacts, minimal changes, attachments, read-only PostgreSQL and Tryton/Coog conventions. Artifacts contain conclusions, never a chain of thought.

The default single worker runs jobs sequentially. Different browsers can submit different requests to the persistent queue; concurrent operations on the same request are guarded. Shared visibility does not provide per-user authentication or privacy.

Git network operations have a ten-minute timeout each. Full synchronization has a separate twenty-minute limit; an initial large download can take longer than an analysis.

## Operations

```sh
docker compose ps
docker compose logs --tail=100 backend worker agent-runtime
docker compose down
```

`down` preserves volumes. Back up the application database, `app-data` (including its encryption key), uploads, AI sessions and credentials together. Keep mirrors and worktrees for historical baselines. Do not use `down -v` on an instance you need to preserve.

Volume names use the `spechelper` prefix. Automatic source modification, PR creation, business writes and multi-tenant management are not implemented. Infrastructure controls access to the entire instance.

## Development and checks

Use Python 3.12+, Node.js 22+ and `uv`:

```sh
uv sync --project backend --python 3.12
uv run --project backend python backend/manage.py migrate
uv run --project backend python backend/manage.py runserver 127.0.0.1:8018
```

Set `BACKEND_URL=http://127.0.0.1:8018` in `frontend/.env.local`, then:

```sh
cd frontend
npm ci
npm run dev
```

A local worker needs `RUNTIME_URL`, `RUNTIME_TOKEN` and a `SPECHELPER_DATA_DIR` consistent with the runtime. Compose is recommended for exercising actual isolation.

```sh
cd backend
uv run pytest -q
uv run ruff check --config pyproject.toml . ../runtime
uv run python manage.py makemigrations --check --dry-run
```

PostgreSQL integration tests use `SPECHELPER_TEST_POSTGRES_DSN` and create temporary schemas and roles. Use only a disposable test database. These tests are explicitly skipped when the variable is absent.

```sh
cd frontend
npm run build
npm run typecheck
npm run test:e2e
```

Install Chromium with `npx playwright install chromium` in `frontend`. Set `PLAYWRIGHT_CHANNEL=chrome` to use installed Chrome. Tests require the local servers described above. Add the frontend origin to `TRUSTED_ORIGINS` for a port other than 3000. They create and remove `[E2E]` fixtures in the local development database and use controlled AI results. Never target the connected team instance. See [implementation notes](docs/implementation.md) for historical runtime checks.

Check Linux isolation and the complete workflow without an AI account:

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

The [v1.2 audit](docs/acceptance-v1.2.md) distinguishes deterministic checks from connected-account validation. [v1.1](docs/acceptance-v1.1.md) and [v1.0](docs/acceptance.md) retain historical evidence. Public reports are anonymized, dated tests, not connections or latency guarantees supplied with a new installation.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [publication preparation](docs/publication.md).
