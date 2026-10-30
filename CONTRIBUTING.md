# Contributing to SpecHelper

Contributions to SpecHelper-owned code are offered under the [MIT License](LICENSE).
Preserve [third-party notices](THIRD_PARTY_NOTICES.md) and do not add material with
unknown provenance or licensing. Report vulnerabilities through [SECURITY.md](SECURITY.md).

## Make a focused change

Describe the problem, resulting behavior and checks performed. Keep documentation
cleanup separate from functional changes. Preserve existing migrations, immutable
results, frozen references, independent role sessions, read-only resources and
explicit publication approval. Do not commit credentials, private corpora, generated
results, provider sessions, backups or screenshots containing team data.

See [Development](docs/development.md) for setup and executable checks. Use
disposable data for tests; controlled provider responses are not live quality evidence.

## Language and translations

Write code identifiers, comments, docstrings and documentation in English. Keep
fixed interface strings in `frontend/src/locales/en.json` and `fr.json`, with matching
keys and interpolation placeholders. Use `useI18n().t()` and `dateLocale`; do not
translate user input or generated business content in the browser.

Backend artifact labels use `core.i18n.translate` and the language frozen for the
analysis. Preserve exact source quotations, filenames and identifiers. Changing
instance language must not rewrite earlier artifacts or historical migrations.

## Maintain the documentation

Update the guide that owns a behavior: installation, configuration, usage,
architecture or development. Link to that guide instead of copying its full rules.
The README remains a short entry point describing implemented behavior.

Describe the current application without referring to past product generations
or announcing unimplemented roadmap items. Dependency versions, protocol identifiers
and other necessary technical references remain valid. Keep release history in Git
and [CHANGELOG.md](CHANGELOG.md), outside the getting-started path.

Do not create a permanent acceptance report for every delivery. Preserve a dated
record only for meaningful security, licensing or non-repeatable evaluation evidence;
label its date, scope, failures and limits. Never promote an old report into current
approval. The small [evidence collection](docs/development.md#optional-evaluations)
serves that purpose; superseded guides remain retrievable from Git.

From the repository root, check documentation links and examples:

```sh
python3 scripts/check_documentation.py
```

This offline check validates local targets, anchors, shell syntax and named scripts.
It does not verify external URLs, execute deployments or certify application behavior.
