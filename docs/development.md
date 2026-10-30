# Development

Start with [CONTRIBUTING](../CONTRIBUTING.md) for contribution and documentation rules.
Use fictional data and separate development storage. Never run mutating fixtures,
active scans or publication tests against a team instance.

## Repository layout

| Path | Contents |
| --- | --- |
| `frontend/` | Next.js/React interface, translations and Playwright tests |
| `backend/` | Django/Ninja API, models, migrations, orchestration and tests |
| `runtime/` | Provider adapters, resource brokers, sandbox and runtime smoke probes |
| `scripts/` | Documentation checks, security runners and opt-in evaluation tools |
| `security/` | Scanner rules, applicability reviews and exact exceptions |
| `docs/` | Current guides and a small set of dated evidence records |

## Local setup

The reference images and CI use Python 3.12 and Node.js 22. Install uv and the frontend
package manager, then use frozen dependency files. Docker Compose is the simplest way
to exercise the full isolated runtime; see [Installation](installation.md).

For API/UI development without provider execution, from the repository root:

```sh
uv sync --project backend --python 3.12 --frozen
export SPECHELPER_DATA_DIR="$PWD/.local/development"
uv run --project backend python backend/manage.py migrate
uv run --project backend python backend/manage.py runserver 127.0.0.1:8018
```

Use a separate terminal for the frontend:

```sh
cd frontend
npm ci
BACKEND_URL=http://127.0.0.1:8018 npm run dev
```

The native backend defaults to SQLite when application PostgreSQL is not configured.
Keep the data-directory setting in every API/worker terminal. Do not inherit deployment
PostgreSQL credentials into this development process. The frontend proxies requests to
`BACKEND_URL`; a locally running API/UI alone does not supply the sandbox runtime or
all provider capabilities. Keep runtime integration in a separate Compose project
rather than removing security checks to make native execution work.

## Backend checks

From `backend/`:

```sh
uv run ruff check --config pyproject.toml . ../runtime
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
```

Most tests use fake provider transports or synthetic responses and need no AI account.
A passing mocked pipeline proves its tested orchestration contract, not model accuracy,
subscription availability or live CLI compatibility.

Concurrency and read-only database probes need disposable PostgreSQL. The primary test
application database must also be PostgreSQL for real row-lock tests; the optional
`SPECHELPER_TEST_POSTGRES_DSN` points to the separate disposable SQL fixture database.
Give the test runner permission to create/drop only its disposable databases. Never
point either setting at business or production data. Without these fixtures some
PostgreSQL-specific tests skip; report those skips instead of claiming lock coverage.
Use the test modules' fixture requirements when running a focused subset.

## Frontend checks

From `frontend/`:

```sh
npm ci
npm run typecheck
npm run build
```

Browser tests require a running frontend; the configuration does not start it.
They use `E2E_BASE_URL` (default `http://localhost:3000`). Some tests mock API responses;
others create or modify records through a real backend. Use an isolated development
instance and read the chosen fixture before running the full suite.

For example, run a compiled frontend in one terminal with `npm run start`, then the
fully mocked conversation/progress fixtures in another:

```sh
npm run test:e2e -- persistent-discussion.spec.ts observed-progress.spec.ts --project=desktop
```

Install the Chromium browser required by Playwright when necessary:

```sh
npx playwright install chromium
```

`PLAYWRIGHT_CHANNEL` can select an installed compatible browser. The complete suite
also covers responsive layouts, access controls, Markdown/XSS, editing, connectors,
reports and cancellation. Keep the actual test counts and skipped coverage in the
change report, rather than maintaining a permanent count in these guides.

## Runtime and security checks

Use [Security testing](security-testing.md) for source/dependency/image scanners,
disposable DAST and HTTPS checks. Scanner versions, gates and schedules live in the
[security workflow](../.github/workflows/security.yml) and machine-readable registers.

Runtime tests must use the actual built Linux image and namespace controls. Source-only
unit tests cannot verify child UID/capabilities, filesystem and egress restrictions.
Smoke modules live under `runtime/`; some exercise authentication or real provider
inference. Inspect each module's flags and prerequisites first. Use a separate Compose
project with synthetic sources and explicitly authorized accounts. Do not import host
credentials or relax sandbox settings to make a probe pass.

Provider inference, CLI updates, external writes and active scans are opt-in operations.
Report quota errors, missing credentials and unavailable native probes honestly; never
replace them with a simulated successful result.

## Documentation checks

From the repository root:

```sh
python3 scripts/check_documentation.py
```

This offline checker validates relative links and Markdown anchors, shell syntax,
referenced runtime modules and npm script names. It does not fetch external URLs or
execute installation commands. Verify changed examples against the current configuration
and run the safe commands appropriate to the change.

For Compose syntax and substitutions, without exposing resolved secret values:

```sh
docker compose --env-file .env.example config --quiet
```

## Optional evaluations

The qualification harness validates the synthetic input corpus without inference:

```sh
python3 -m scripts.qualification.harness validate
python3 -m scripts.qualification.harness --help
python3 scripts/evaluation/reliability_benchmark.py --help
```

Additional native evaluation commands can consume significant model quota. They require
explicit configuration, retained source baselines and disposable database fixtures.
Do not treat a synthetic corpus, a completed CLI call or an agent-assisted review as
independent human acceptance of real business answers. The indexing experiment is
not enabled in production.

Retained evidence is deliberately small:

- [Security review](evidence/security-review.md): dated attack/re-test scope and residual limitations.
- [Publication review](evidence/publication-review.md): licensing and privacy review scope.
- [Qualification observations](evidence/qualification.md): failed/incomplete quality trials and indexing limits.

These are historical observations, not current installation instructions or certification.
Git retains superseded specifications and implementation reports.
