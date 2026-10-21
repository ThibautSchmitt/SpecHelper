# Publication review — 2026-10-21

Verdict: **PASS WITH WARNINGS** for the source snapshot, with third-party licensing
scope retained below. No remote repository, commit or push has been created.

This report covers the refreshed publication snapshot, including English/French
localization. Select **Admin → Instance → Application language**; French remains
the default. Each request retains its creation language, and existing artifacts
are not rewritten. See [localization verification](docs/localization.md).

## Files reviewed

The publication contains 141 project-owned files, including this report. Sources,
tests, migrations, configuration and documentation were read; both dependency locks
were parsed. The three working PDF briefs were parsed (36 pages) and are excluded
from distribution. Installed dependency/cache/build files and private runtime data
are excluded; dependency license metadata was inspected separately.

## Secrets and private references

- `detect-secrets 1.5.0` scanned the candidate and tracked source files.
- Eleven findings in nine files were reviewed: eight are synthetic test fixtures
  or the disposable CI database password; three are translated "Password" labels.
  None is a live account credential.
- Two local secret values were compared against the publication files without
  printing them; no occurrence was found.
- Instance-specific session/request IDs, validation repository references, branch
  references and business model names were removed from public acceptance reports.
- Original reports, local keys, uploads, results, sessions and backups remain local
  and are excluded from Git. The public snapshot contains no home-directory paths
  or references to private repositories/accounts identified during this review.

## Licensing and packaging

SpecHelper-owned code is MIT. Python/npm metadata and LICENSE agree. Adapted
shadcn/ui components retain the upstream MIT notice. Dependencies retain their
licenses; see THIRD_PARTY_NOTICES.md. In particular, pglast is GPL-3.0-or-later,
and psycopg is LGPL. The combined backend/container is not exclusively MIT.

Locks refer to public package registries. Working PDF briefs and generated agent
instructions are excluded. Docker images carry the project license/notices.
CONTRIBUTING, SECURITY, GitHub issue/PR templates and a checks-only
GitHub Actions workflow are supplied without account-specific links.

## Verification

- The initial clean copy passed `npm ci --offline`, `uv sync --frozen --offline`
  and a frontend build without the original `.env.local`. Dependency versions are
  unchanged by localization.
- Current backend suite: **99 passed** on disposable PostgreSQL 17, including
  business database integration and language migration tests.
- Current frontend: production build and TypeScript checks pass.
- Browser: **26 desktop/mobile scenarios pass** against isolated local fixtures,
  including both languages, persistence, errors and workflow exports. This run
  used installed Chrome via the documented channel override.
- A restored database migration and the deployed migration preserve all nine
  checked data fingerprints. Historical request and version languages are French.
- Linux isolation, deterministic Codex comparison and Claude workflow checks pass.
- Ruff, migration application, Python lock consistency and Compose validation pass.
- Git index whitespace check and exclusion checks pass. The branch is `main`,
  without remotes or commits. No prior Git history was present to sanitize.

The GitHub Actions workflow has not run on GitHub; it will run after a repository
is created and the source is sent there. Scanning and review reduce exposure risk
but do not establish the absence of every possible vulnerability.

## Unreadable Files

Unreadable count: **0**.

All publication files are readable UTF-8. The excluded working PDFs were readable.
There is no unreadable-file sidecar because the count is zero.
