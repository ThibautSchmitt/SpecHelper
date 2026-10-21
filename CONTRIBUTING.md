# Contributing to SpecHelper

Contributions to SpecHelper-owned code are offered under the repository's MIT license. Preserve third-party notices and do not add code with unknown provenance or licensing.

## Setup

The [README](README.md) describes Docker Compose installation and product usage.
The runtime requires Linux, Bubblewrap and namespaces. Use Docker Desktop on
macOS/Windows or Docker Engine on Linux. Native development assumes Unix, Python
3.12+, Node.js 22+ and `uv`. Deterministic tests require no AI account.

Run each command block below from the repository root unless stated otherwise.
Start the local API in one terminal:

```sh
uv sync --project backend --python 3.12 --frozen
uv run --project backend python backend/manage.py migrate
uv run --project backend python backend/manage.py runserver 127.0.0.1:8018
```

Set `BACKEND_URL=http://127.0.0.1:8018` in `frontend/.env.local`, then start the
frontend in another terminal:

```sh
cd frontend
npm ci
npm run dev
```

A local worker needs `RUNTIME_URL`, `RUNTIME_TOKEN` and a `SPECHELPER_DATA_DIR`
consistent with the runtime. Compose is recommended for exercising actual
isolation. See [implementation and runtime checks](docs/implementation.md).

## Checks

```sh
uv sync --project backend --python 3.12 --frozen
cd backend
uv run pytest -q
uv run ruff check --config pyproject.toml . ../runtime
uv run python manage.py makemigrations --check --dry-run
```

Full PostgreSQL integration tests require `SPECHELPER_TEST_POSTGRES_DSN` on a disposable database: they create and remove objects and roles. Never target a production instance or business database.

```sh
cd frontend
npm ci
npm run build
npm run typecheck
npx playwright install chromium
```

For browser tests, start the local API and frontend described above, then run
`npm run test:e2e` from `frontend`. Playwright Chromium is the default;
`PLAYWRIGHT_CHANNEL=chrome` selects installed Chrome. The default frontend URL
is `http://localhost:3000`; use `E2E_BASE_URL` for another address and add its
origin to the API's `TRUSTED_ORIGINS` when using a different port.

Tests create and remove `[E2E]` fixtures in the default local development database
and use controlled AI results. Never run them against the Docker deployment
connected to team accounts. For Linux isolation, provider adapters, database
capabilities and process-reaping checks, use the commands under
[runtime checks](docs/implementation.md#runtime-checks).

## Proposed changes

- Explain the problem, resulting behavior and validation performed.
- Keep changes focused and preserve historical migrations.
- Preserve frozen baselines, immutable versions and read-only boundaries.
- Write code identifiers, comments, docstrings and documentation in English. Put interface text in the English/French translation catalogs and keep both languages complete.
- Respect the instance language for the interface and freeze analysis language at request creation. Never rewrite earlier artifacts when changing the setting.
- Never attach credentials, real results, private files, backups, AI sessions or screenshots containing team data.

For security issues, follow [SECURITY.md](SECURITY.md).
