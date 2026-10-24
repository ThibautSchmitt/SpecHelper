> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# English and French

Select **Settings → General → Application language**, then save the settings. The
setting belongs to the shared instance. Open browsers refresh it within 15 seconds;
the browser saving it updates immediately. French is the default.

The setting controls interface labels, status notices, dates, errors, and the output
language of new analyses. Requests retain their creation language through questions,
answers, comparison, review and later discussion. Ticket and goal headings follow
that language. Changing the setting never rewrites existing artifacts or user text.
Source identifiers, schemas, repository paths and code examples keep their original
meaning and project conventions.

## Maintaining translations

Source code, comments, docstrings, internal instructions and documentation are in
English. English strings are translation keys. The frontend catalogs are
`frontend/src/locales/en.json` and `fr.json`; their keys and interpolation
placeholders must match. Use `useI18n().t()` for application text and `dateLocale`
for dates. Do not translate user messages or model-generated business content in
the browser.

Backend artifact labels and fixed constraints use `core.i18n.translate` with the
request language. Analysis instructions explicitly carry the frozen output language
to every participating role. The Writer must also write every narrative field of
`ticket.md` and `goal.md` in that language, rephrasing observations from sources in
another language. Filenames, paths, symbols, commands and exact quotations stay
unchanged. Migration 0009 refreshes this instruction on existing installations
without changing activation flags or published artifacts.
API error strings remain English; the interface
translates recognized messages, including historical French system notices.

Historical French seed content lives in `backend/core/locales/v11.fr.json`,
`v12.fr.json` and `legacy_migrations.fr.json`. These are immutable migration data,
not current instructions. Preserve their contents when maintaining migrations.
Migration 0007 backfills old request/version languages with French; 0008 updates
internal instructions to English while preserving profile and skill activation.

## Verification on 2026-10-21

- Backend suite on disposable PostgreSQL 17: **99 passed**. Tests include settings
  validation, both output languages, request language persistence, all comparison
  roles, immutable artifacts and migration preservation. English/French download
  checks exercise both normal and comparison workflows, including artifact bodies,
  headers, technical summaries and preserved code identifiers.
- Playwright with installed Chrome: **26 passed** across desktop and mobile.
  Coverage includes catalog/placeholder parity, historical dynamic notices,
  language switching, settings persistence, translated errors and workflow exports.
- Frontend production build, TypeScript, Ruff and migration consistency passed.
- The deployed localhost instance passed an additional browser check: Admin
  switches English/French, reload preserves the setting, and a second browser
  receives the change within the refresh interval. Desktop/mobile layouts passed;
  the initial French setting was restored afterward.
- A restored local database migrated successfully. Fingerprints matched for all
  nine checked data groups, including requests, versions, artifacts, sessions,
  environments, repository baselines, database connections and GitHub connection.
- Linux Bubblewrap isolation and deterministic Codex comparison / Claude workflow
  checks passed, including clarification, session resumption and frozen exports.

Deterministic CLI fixtures establish application behavior and isolation, not the
quality or language accuracy of a live model's response.
