# Contributing to SpecHelper

Contributions to SpecHelper-owned code are offered under the repository's MIT license. Preserve third-party notices and do not add code with unknown provenance or licensing.

## Setup

The [README](README.md) describes Docker Compose and local development. The runtime requires Linux, Bubblewrap and namespaces. Use Docker Desktop on macOS/Windows or Docker Engine on Linux. Native development assumes Unix. Deterministic tests require no AI account.

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

For browser tests, start the local API and frontend described in the README, then run `npm run test:e2e`. Playwright Chromium is the default; `PLAYWRIGHT_CHANNEL=chrome` selects installed Chrome. Tests use local database fixtures. Never run them against the Docker deployment connected to team accounts.

## Proposed changes

- Explain the problem, resulting behavior and validation performed.
- Keep changes focused and preserve historical migrations.
- Preserve frozen baselines, immutable versions and read-only boundaries.
- Write code identifiers, comments, docstrings and documentation in English. Put interface text in the English/French translation catalogs and keep both languages complete.
- Respect the instance language for the interface and freeze analysis language at request creation. Never rewrite earlier artifacts when changing the setting.
- Never attach credentials, real results, private files, backups, AI sessions or screenshots containing team data.

For security issues, follow [SECURITY.md](SECURITY.md).
