# Preparing publication on GitHub

Local preparation dated October 21, 2026, without creating a remote repository or pushing. The GitHub account or organization, repository name and initial commit identity will be chosen before publication. No account has been selected. The [review report](../SANITIZATION_REPORT.md) describes scope and checks.

## Reviewed scope

Sources, tests, migrations, configuration and Python/npm lockfiles were read or analyzed, along with documentation and three working PDF briefs. Installed dependencies and generated files are not project sources; their license metadata was reviewed. Local instance data is outside the distribution.

Public acceptance reports are anonymized. Originals remain only in local storage excluded from Git. Request/session identifiers, validation repository references and instance-specific business names were removed. Synthetic test values remain as fixtures.

## License

SpecHelper-owned code is MIT-licensed, with `Copyright (c) 2026 SpecHelper contributors`. Python and npm metadata use the MIT identifier. Dockerfiles include license notices for subsequent builds. Adapted shadcn/ui components retain upstream MIT attribution.

Dependencies retain their licenses; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), particularly pglast (GPL) and psycopg (LGPL). The project's MIT license does not make every dependency or built image MIT-licensed.

## Excluded content

- `.local`, backups, SQLite databases, uploads, results and AI sessions.
- `.env` and local variants; only `.env.example` is published.
- Credentials, tokens, keys, dumps and account-access files.
- `node_modules`, `.venv`, `.next`, caches, test reports and generated metadata.
- Working PDF briefs; [specification.md](specification.md) describes the public scope.
- Generated agent instructions specific to the development environment.

## Checks and CI

Local checks cover backend tests, Ruff, TypeScript, the Next.js build, Python lock consistency, Compose validation and files intended for Git. Browser tests do not require `rtk`; Playwright Chromium is the default, with Chrome selectable through `PLAYWRIGHT_CHANNEL`.

GitHub Actions runs backend tests against disposable PostgreSQL, Ruff, migration checks and frontend build/typecheck. It neither deploys nor publishes images, uses no AI account and requires no GitHub secrets. Its execution can only be verified once a remote repository exists.

Documentation and code prose are maintained in English. **Admin → Instance → Application language** selects English or French for the interface and new analyses. French remains the default for existing installations. Each request retains its creation language; changing the setting does not rewrite historical artifacts. Validation of this feature is separate from the dated publication snapshot's checks.

## Deferred final step

Before the first upload, select the GitHub owner, repository name and commit identity, review staged files and third-party notices, then create the commit and configure the remote. No push or GitHub repository creation was performed during this preparation.
