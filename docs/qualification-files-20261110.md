# File qualification — 10 November 2026

These are dated observations on the local test installation, not security
certification or evidence for every possible document. Fixtures are genuine,
synthetic files with four independently specified facts per file. Expected answers
were kept outside the prompts. Private fixtures, operation plans and raw reports
remain outside the published repository.

## Upload and native reading

| Run | Real operations | Observed result |
| --- | --- | --- |
| Initial allowlist | PDF, DOCX, PNG, JPEG, Markdown and TXT with both configured AIs | 12 uploads and byte-exact downloads; cross-conversation download refused. 7/12 native answers exact. |
| Initial unsupported files | Binary DOC, XLSX and SQL | All three refused under the initial allowlist. DOC remains unsupported. |
| Targeted retry after fixes | ChatGPT: PDF, PNG, Markdown, TXT; Antigravity: PDF | 5/5 native answers exact. This is a retry of failures, not a second complete twelve-case run. |
| Added formats | XLSX and SQL with both configured AIs | 4 uploads/downloads byte-exact and 4/4 native answers exact. No SQL execution or independent analysis requested. |

The configured models were ChatGPT/Codex `gpt-6.1-sol` and
Antigravity `gemini-3.8-flash-low`. A conversation-prompt mapping omitted actual
sandbox attachment paths; those are now provided without exposing host paths.
Antigravity's native command allowlist also omitted `pdftotext`; this existing
isolated PDF reader is now allowed. Initial failures are retained rather than
removed from the evidence. A retry interrupted by Docker disk exhaustion was
recorded separately, then rerun after clearing only identified unused build caches.
Owned reading-test conversations were archived, not deleted.

## Approved external publication and remote downloads

Two explicitly approved neutral tickets were created on the local GitLab test/test
project and GLPI Root entity. Each selected exactly six files: PDF, DOCX, PNG, JPEG,
Markdown and TXT. An uploaded TXT witness was deliberately excluded. No generated
documents, sensitive data, source changes or independent analysis were requested.

The publication bench observed one create per destination despite double
confirmation, the chosen connection/destination, six claimed transfers and one
durable conversation publication event each. Independent remote downloads exposed
limits that the engine result alone did not establish:

| Destination | Download observation |
| --- | --- |
| GitLab | Six files downloaded. PDF, DOCX, PNG, Markdown and TXT were byte-exact. JPEG bytes differed because metadata was added; dimensions and decoded pixels were identical. |
| GLPI | PDF, DOCX, PNG, JPEG and TXT were byte-exact. Markdown had only a document record, with no stored filename/path or binary; its download failed. |

The excluded witness was absent. The GLPI instance's native `DocumentType`
catalogue allows XLSX but does not allow Markdown or SQL. SpecHelper previously
trusted the returned document ID. The correction now checks that catalogue before
publication and confirms actual storage metadata/checksum after upload, preserving
uncertainty rather than presenting a missing file as a successful transfer.
The existing external records were retained for inspection; no remote document
policy was changed and no existing ticket was deleted or rewritten.

Two further neutral publications were explicitly approved after adding XLSX/SQL:
GitLab test/test received `case.xlsx` and `case.sql`; GLPI Root entity received
`case.xlsx`. All three remote downloads were byte-exact against the selected
originals. The actual creator matched each selected connection's native identity;
the excluded witness was absent. GLPI's SQL file remained in its conversation and
was correctly unavailable for transfer under that instance's native policy.

Each new case exercised double confirmation with one external create. Re-running
the same operation plans in a separate process returned the existing publications
with zero create attempts and no additional file transfers. The original six-file
operations were also resumed without new creates. That proves replay preservation,
not retroactive success for the missing GLPI Markdown file. The new policy initially
blocked replay of that old operation; the correction now compares the immutable
snapshot/digest before applying current policy to any unstarted transfer. Modified
content or file selections still conflict, and denied pending files are not sent.

The four owned publication conversations were archived; publications and source
links remain accessible. A live browser check confirmed French **Ouvrir**, provider
logos and direct browser-reachable external URLs, including localhost for GLPI.
Real GitHub/Jira execution remains deferred.

## Security and scope

Automated regressions exercise accepted file round trips, scope restrictions,
read-only storage, binary SQL rejection, bounded expansion, invalid compression,
path traversal, macros, embedded objects and external-data workbook containers.
Publication regressions exercise destination format refusal, no AI spend when
Markdown is disallowed, and GLPI's empty or mismatching document responses.

The targeted format/provider/document/discussion run passed 212 tests. A later
publication/replay/format subset passed 202 tests with one PostgreSQL-only concurrency
case skipped on local SQLite. Twelve targeted browser tests passed against the
production frontend on desktop/mobile, including French/English light/dark ticket
flows and refusal of generated Markdown without AI calls. Initial browser attempts
were blocked by a missing bundled Chromium and the macOS sandbox; the completed run
used installed Chrome with execution permission. TypeScript, Ruff and the offline
documentation checker passed. The broader local backend run passed 1,745 tests with 39 skipped and one existing
Starlette deprecation warning. It started before the final replay adjustment; the
publication/replay subset was rerun after that adjustment. These counts overlap
and must not be added together.

Hosted verification of source commit `864a0d9` completed the
[Security campaign](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42748420225)
successfully. In [Checks](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42748420103),
both desktop/mobile frontend jobs passed; the PostgreSQL backend recorded 1,785
passes and one failure in an existing Git-baseline test. That assertion selected
the final list item as the fork, although database updates do not guarantee that
ordering. The test now deliberately puts the fork first and checks retained SHAs
by repository identity. This is a test correction, not a change to Git synchronization;
the two local Git tests passed after this correction. Hosted verification of
`d974046` then passed every job in
[Checks](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42765863086)
and the [Security campaign](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42765862972).

The allowlist is intentional. Read-only access protects source integrity but does
not eliminate parser vulnerabilities or prompt injection. No antivirus service,
universal malicious-file scanner or guarantee of harmless content was added.
The tests use small valid fixtures and targeted malformed cases; they do not
establish coverage for every PDF/image/Office variant, scanned PDFs, encrypted
documents, all encodings, large business workbooks or every provider configuration.

See [configuration](configuration.md), [usage](usage.md#optional-files), and
[publication qualification](publication-qualification.md) for current behavior.
