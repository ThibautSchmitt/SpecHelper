# Publication review — 2026-10-22

Verdict: **PASS WITH WARNINGS** for the source snapshot, with third-party licensing
scope retained below. The reviewed source is prepared in the local publication checkout; remote push status is reported separately.

This report covers the refreshed publication snapshot, including v1.4 multi-source and assistant connections and English/French
localization. Select **Settings → Instance → Application language**; French remains
the default. Each request retains its creation language, and existing artifacts
are not rewritten. See [localization verification](docs/localization.md).

## Files reviewed

The publication contains 182 project-owned files, including this report. Sources,
tests, migrations, configuration and documentation were read; both dependency locks
were parsed. Installed dependency/cache/build files and private runtime data
are excluded; dependency license metadata was inspected separately.

## Secrets and private references

- `detect-secrets 1.5.0` scanned the candidate and tracked source files.
- Twenty-two findings in fifteen files were reviewed: nineteen are synthetic test
  fixtures or the disposable CI database password; three are translated "Password" labels.
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

Locks refer to public package registries. Generated agent instructions are excluded. Docker images carry the project license/notices.
CONTRIBUTING, SECURITY, GitHub issue/PR templates and a checks-only
GitHub Actions workflow are supplied without account-specific links.

## Verification

- The initial clean copy passed `npm ci --offline`, `uv sync --frozen --offline`
  and a frontend build without the original `.env.local`. The v1.3 locks also include PyYAML and Markdown preview dependencies, with
  their licenses recorded in THIRD_PARTY_NOTICES.md.
- Current backend suite: **288 passed** on disposable PostgreSQL 17, including
  business database integration and language migration tests.
- Current frontend: production build and TypeScript checks pass.
- Browser: **52 desktop/mobile scenarios pass** against isolated local fixtures,
  including both languages, persistence, errors and workflow exports. This run
  used installed Chrome via the documented channel override.
- A restored database migration and the deployed migration preserve all nine
  checked data fingerprints. Historical request and version languages are French.
- Linux isolation, deterministic Codex comparison and Claude workflow checks pass.
- Ruff, migration application, Python lock consistency and Compose validation pass.
- Git index whitespace check and exclusion checks pass. The publication branch is `main`. No prior external Git history was imported.

The GitHub Actions workflow has not run on GitHub; it will run after a repository
receives the source update. Scanning and review reduce exposure risk
but do not establish the absence of every possible vulnerability.

A separate deployed desktop/mobile check and an actual GLPI 11.0.7 ticket
creation/reconciliation check pass. See [v1.4 acceptance](docs/acceptance-v1.4.md) and
[v1.3 connector acceptance](docs/acceptance-v1.3.md)
for the distinction between provider contract fixtures and vendor-service tests.

## Unreadable Files

Unreadable count: **0**.

All publication files are readable UTF-8.
There is no unreadable-file sidecar because the count is zero.
