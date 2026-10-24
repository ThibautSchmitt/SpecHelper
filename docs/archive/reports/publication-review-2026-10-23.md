> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# Publication review — 2026-10-23

Verdict: **PASS WITH WARNINGS** for the source snapshot, with third-party licensing
scope retained below. The reviewed source is prepared in the local publication checkout; remote push status is reported separately.

This report covers the refreshed publication candidate, including v2.2 guided business
clarification, immutable human-confirmed decisions, explicit conflict review, targeted
reanalysis and business-result validation, as well as the v2.1 conversational
library assistant, inactive drafts, shared-queue demonstrations, declaration import/export
and historical restoration, alongside the v2.0 versioned library, environment assignments
and provider model catalog and v1.9 access protection,
encrypted CLI credentials, isolated provider execution, hostile-file validation and
security CI, together with consolidated settings, environment-owned ticket connectors,
official non-inference Codex quota reads, v1.8 appearance, automatic role-based analysis,
clearer task visibility, project questions and versioned environment context,
independent analysis roles and verification and English/French
localization. Select **Settings → General → Application language**; French remains
the default. Each request retains its creation language, and existing artifacts
are not rewritten. See [localization verification](../guides/localization.md).

## Files reviewed

The publication candidate contains 328 project-owned files, including this report. Sources,
tests, migrations, configuration and documentation were read; both dependency locks
were parsed. Installed dependency/cache/build files and private runtime data
are excluded; dependency license metadata was inspected separately.

## Secrets and private references

- `detect-secrets 1.5.0` scanned the candidate and tracked source files.
- Twenty-eight findings in twenty files were reviewed: twenty-five are synthetic test
  fixtures or the disposable CI database password; three are translated "Password" labels.
  None is a live account credential.
- The v1.9 candidate and full publication Git history also pass Gitleaks 8.30.1.
  New fixtures use clearly synthetic values; no blanket test-source exclusion was added.
- Configured connection credentials were compared against the publication files without
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
GitHub Actions workflows are supplied without account-specific links. Security jobs
include source, dependency, image, runtime and disposable authenticated DAST checks.

## Verification

- The initial clean copy passed `npm ci --offline`, `uv sync --frozen --offline`
  and a frontend build without the original `.env.local`. The v1.3 locks also include PyYAML and Markdown preview dependencies, with
  their licenses recorded in THIRD_PARTY_NOTICES.md.
- v1.8 backend suite: **443 passed** on disposable PostgreSQL 17, including
  business database integration and language migration tests.
- Current frontend: production build and TypeScript checks pass.
- The v1.8 complete browser suite passed **118 desktop/mobile scenarios** against isolated local fixtures,
  including both languages, persistence, errors and workflow exports. This run
  used installed Chrome via the documented channel override. The subsequent queue-card
  refinement passes 18 focused browser scenarios, including clipped long text,
  provider artwork, public roles, state transitions and reduced motion.
- A restored database migration and the deployed migration preserve all sixteen
  checked historical data fingerprints. Historical request and version languages are French.
- Linux isolation, deterministic TypeScript/Codex/Claude comparison, versioned context, question/documentation/request handoff and Claude/PostgreSQL workflow checks pass. Connected v1.6 attempts were quota-blocked; no real-model analysis quality is claimed.
- Ruff, migration application, Python lock consistency and Compose validation pass.
- Git index whitespace check and exclusion checks pass. The publication branch is `main`. No prior external Git history was imported.

GitHub Actions results for this source update have not been inspected; the workflow
runs when a repository receives the update. Scanning and review reduce exposure risk
but do not establish the absence of every possible vulnerability.

The [v1.9 acceptance report](acceptance-v1.9.md) records the current 510-test
backend result, browser re-tests, encrypted-credential and database-copy rehearsals,
real HTTPS checks and executed security scans. Image reports retain their OS findings
under exact, expiring applicability reviews; no zero-vulnerability claim is made.

The [v2.0 acceptance report](acceptance-v2.0.md) records the subsequent 536-test
backend run, final focused security checks, all 138 browser cases across the full
run/re-tests and copy-based migration preservation. Gitleaks reports no candidate
secrets; Semgrep covers 149 production files with no findings or parse errors,
including all new library/model/runtime interfaces. Publication candidate preparation
does not imply a commit, remote push or production deployment.

The [v2.1 acceptance report](acceptance-v2.1.md) records 585 passing backend
tests, the 146-case full browser run and subsequent coverage of four additional
queue-localization cases, plus 28 passing production-build browser checks.
Migration 0025 preserves all original values in 34 checked tables and 384 rows on
a protected copy. Current candidate scans find no secrets; six Semgrep rules cover
153 production files without findings or parse errors. The real Linux containment
probe passes again. Provider generation/demo responses are controlled test fixtures;
these checks do not claim a successful live paid-inference run.

The [v2.2 acceptance report](acceptance-v2.2.md) maps all business-clarification
requirements to schema, API, worker, artifact and browser checks. The final backend
run passes 635 tests with one host-only Linux skip, covered by the actual runtime
probe. Migration 0026 preserves original data in 36 tables and 396 rows on a
protected copy. Current scans report no candidate secrets and no findings or parse
errors across 159 production files under six local Semgrep rules. The report
distinguishes controlled provider responses from actual browser-to-API verification
and records 176 passing full-suite browser cases and 52 passing production-build
browser cases. No source-writing permission or
automatic production deployment is added.

A separate deployed desktop/mobile check and an actual GLPI 11.0.7 ticket
creation/reconciliation check pass. See [v1.8 acceptance](acceptance-v1.8.md), [v1.7 acceptance](acceptance-v1.7.md), [v1.6 acceptance](acceptance-v1.6.md) and
[v1.3 connector acceptance](acceptance-v1.3.md)
for the distinction between provider contract fixtures and vendor-service tests.

## Unreadable Files

Unreadable count: **0**.

All publication files are readable UTF-8.
There is no unreadable-file sidecar because the count is zero.
