# Publication review — 23 October 2026

This record preserves the scope of the original source, privacy and licensing review.
It is not a new scan of the current tree or a legal opinion. Superseded implementation
chronology is recoverable from Git history rather than kept as active instructions.

## Privacy and source scope

The reviewed publication candidate contained 328 source files. Secret checks covered
the exported source and its Git history. Twenty-eight candidate detections across
20 files were reviewed: 25 were synthetic/CI material and three were translation
strings containing the word Password. Gitleaks and a configured-secret comparison
were also used; actual configured secret values were not printed in reports.
No retained finding established a published live credential within that scope.

Reports were reviewed for instance identifiers, private repositories/branches and
business-specific names. Private test artifacts, databases, credentials and generated
agent instructions were excluded from the publication tree. This review is dated;
future contributions still need their own privacy and secret checks. Synthetic reports
can contain sensitive-looking payloads and must be reviewed before public attachment.

## Licensing obligations retained

The project's own source uses the [MIT license](../../LICENSE). Adapted components
and dependency licensing are recorded in [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md).
The review included the adapted shadcn material, pglast's GPL licensing and psycopg's
LGPL licensing. The application and built images must not be described as exclusively
MIT: dependencies retain their own terms. A public package registry or lockfile does
not grant relicensing rights. Images carry the applicable license/notice files.

The cleanup of old guides does not remove these notices, change package versions or
relicense third-party material. Maintainers must review distribution obligations for
the actual dependency/image set they ship.

## Limits

The assessment used controlled local evidence and agent-assisted review. It did not
certify a remote CI run, every provider subscription or all possible private-data
leaks. Runtime authentication protocol probes are not successful paid inference tests.
Use [Security testing](../security-testing.md) for current gates and
[CONTRIBUTING](../../CONTRIBUTING.md) for publication rules.
