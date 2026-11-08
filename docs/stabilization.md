# Stabilization review

Review date: 6 November 2026. Inspected baseline: `c3b3b7a` and the accompanying
stabilization changes. This is an engineering review of available evidence, not
certification of model accuracy or deployment security.

The later [7 November load and lifecycle qualification](stabilization-final.md)
records the completed PostgreSQL suite, native conversation batches, local retirement,
Docker lifecycle checks and remaining gaps. Use that report for the latest executed
measurements. The baseline findings, CI failures and self-test below remain dated
evidence; they are not a fresh assessment of today's containers or remote CI.
Operational instructions live in [local administration](local-administration.md).

**A stable-release recommendation is withheld.** Existing conversations, independent
analyses and confirmed publication are a coherent scope. The remaining work is
reliability and release validation, rather than additional product modules.

## Acceptance checklist at the review baseline

| Area | Current evidence | Remaining gate |
| --- | --- | --- |
| Ticket creation and resumption (external updating deferred by product decision) | Native REST creation, explicit confirmation, destination validation, selected-document caching and uncertain-creation reconciliation have tests. | External-ticket reading/updating with conflict detection is deferred by explicit product decision. Do not advertise it as implemented; draft resumption and creation reconciliation remain available. |
| Answer quality and provenance | Exact Git commit/blob/line/excerpt checks, retained SQL/document receipts, honest unverified states and separate role contexts are tested. | A reviewed run with real models on a real application, including deliberately unanswerable questions. Source matching and separate contexts do not prove an interpretation correct. |
| Git version consistency | Real local Git tests retain analysis A after synchronization to B. Later investigations in the same conversation can use B without rewriting A's baseline. | Repeat the workflow during a real synchronization and through publication/resumption; PostgreSQL race checks require the disposable database. |
| Sources and secrets | SQL validation, restrictive-role checks, redaction, broker restrictions, hostile Markdown and read-only bindings are covered by code and application tests. | Repeat database grant/row-lock tests and exact-image Linux isolation probes. The latest security image campaign is not green. |
| Long work and recovery | Checkpoint/fencing tests and corrected configured supervisor deadlines cover interrupted work and bounded attempts. | Restart real worker/runtime containers during synthetic work, then verify cancellation, quotas and checkpoint resumption. |
| Business journey | Browser tests and controlled HTTP provider fixtures cover conversation, draft, optional analysis, documents, confirmed publication and lost-response reconciliation. | A real authorized application and test destination, including reviewed documents and an explicitly confirmed publication. External edits/conflict-safe updating are deferred. |

No checkbox is promoted to complete merely because a mock, prompt instruction or
historical security report exists. Tests that require PostgreSQL/Docker are skipped
locally when those prerequisites are unavailable.

## Corrections in this review

- The conversation/library supervisor no longer overrides a configured one-hour
  invocation after roughly five minutes. Analysis-step supervision no longer has an
  unrelated fifteen-minute ceiling. Process budgets remain finite, and expired
  attempts retain exact-attempt cancellation and checkpoint recovery.
- A later investigation can recreate its clean conversation worktree at its newly
  frozen SHA. The Git regression reproduces the previous health-check failure, then
  verifies both B's content and continued access to A's baseline/content.
- Storage preparation has an explicit isolated configuration instead of inheriting
  application networks together with `network_mode: none`. Real Compose rendering
  validates the resulting absence of attached networks.
- An administration link uses a JSX string expression accepted by the static parser.
  Static-analysis failures are not ignored or relabelled as clean scans.
- Regression fixtures reflect the single active draft, centered creation modal,
  optional deep analysis and published-only Tickets view. Hostile Markdown is tested
  in the conversation renderer that actually displays untrusted content.
- PostgreSQL fixtures use valid optional DSN defaults and compatible active-draft
  constraints/connection IDs. Credential-storage tests do not query a real provider
  with a synthetic API key. The reproducible corpus runner invokes standard tools
  directly and does not require the maintainer's terminal proxy.
- Current ticket/deep-analysis/lifecycle browser regressions are explicitly included
  in CI, alongside existing suites. No safety gate or failing scenario is disabled.

## Validation and limits

The initial complete local backend run recorded **1,663 passed, 32 skipped and three
failed**. Its failures were stale provenance/timeout assertions and a prompt-fixture
JSON parser that assumed nothing followed the data block. Corrected targeted runs
passed. The subsequent complete local run passes **1,669 tests with 32 skipped**.
The final worktree correction is additionally covered by the targeted Git/source/
session campaign below; the complete campaign had already started when that
correction was applied. PostgreSQL-dependent skips remain unresolved locally, and
these results do not claim a green remote CI or exact-image security campaign.

The current production frontend build and TypeScript checks pass. The focused
conversation/ticket, context-selection, persistent-session and hostile-content browser
campaign passes **92 tests** across desktop/mobile and English/French.
The separate conversation lifecycle/archive/source-preservation suite passes
**12 additional browser tests**.

Ruff and the no-pending-migrations check pass. No schema migration or dependency was
added. Browser/API fixtures use fictional content and controlled providers; they do
not constitute real paid inference or confirmed writes to a live ticket platform.
Long-deadline regressions advance a controlled clock rather than running an hour of
paid inference. The targeted Git/source/session campaign passes 80 tests with one
PostgreSQL-dependent test skipped.

Docker and the local HTTP endpoint were initially unavailable. They responded in
the subsequent self-test below. The source overlays were deployed after backup and
checks that session, draft and frozen-reference state was preserved. The native
runtime container was not restarted. This deployment reused existing dependency
images; it does not establish a successful clean image build.

## Release blockers recorded from CI

The inspected [Checks run](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42012528818)
and [Security campaign](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42012528770)
failed on the inspected baseline. Their status is not replaced by focused local passes.

Besides the corrected test/configuration issues, the security campaign records:

- Backend image installation cannot find its pinned GitHub CLI Debian package.
- The runtime's exact-image Linux probe fails with a `setresuid` permission error.
- The frontend image gate rejects outstanding package/applicability findings.

Dependency/source scanner reports are separate evidence: that source run reported no
package-advisory or secret findings, but its static parser error still failed the gate.
Those reports do not establish that built OS images are free of relevant findings.
Do not broaden exceptions, loosen runtime isolation or disable scanner enforcement to
obtain a green badge. Fix and retest the exact images.

## Final real-world acceptance journey

Use an explicitly authorized application and a test project on one chosen platform.
Record the commit, connector, destination and resulting external reference.

1. Ask a business question and a technical question; inspect actual cited passages.
2. Ask something absent from the sources; require an explicit unresolved limitation.
3. Run the three independent roles on a precise change, retaining baseline A.
4. Prepare a concise draft, review it, choose optional files and explicitly publish.
5. Simulate a lost provider response in the controlled fixture; verify the same
   publication rather than creating another issue or identical attachments.
6. Synchronize to B, start a new investigation and verify both historical A and new B.
7. Once external updating exists, compare the provider's current version before any
   write. Test unchanged content, a developer's external edit and a lost update
   response; never overwrite or resend blindly.

Retain expected/observed behavior, the exact sources and remaining limits. A live
external write still needs the user's normal final publication confirmation.

## Live self-test on SpecHelper (6 November 2026)

The user deferred external-ticket updating and authorized testing against SpecHelper
itself. A separate local environment uses the public `ThibautSchmitt/SpecHelper`
repository on `main`, frozen at `a7c1af634dbd463010b257a55ce6d61ae15ea4b6`.
The real ChatGPT connection runs `gpt-6.1-sol` with its existing role permissions.
No Antigravity role was added. The external publication was completed only after
the explicit user confirmation recorded in the completion section below.

### Database and runtime boundaries

A disposable PostgreSQL 17 instance, separate from the application database, passes
**34 integration tests** covering restrictive grants, rejected writes, concurrent
discussion/lease handling, the active-draft migration and ticket documents.

The exact deployed runtime image
`sha256:900faeae5fb6cde67ce94159e2de587378e85499a5d767c814bf092c12268d67`
passes `runtime.v19_smoke` and `runtime.v24_smoke` in disposable containers without
real credentials, provider inference, source mounts or external networking. The
probes verify denied source writes, hidden credentials and other sessions, denied
arbitrary networking, enforced seccomp, denied operations from hostile README/PDF/
ticket/database carriers, separate parallel sandboxes and idempotent exact-attempt
cancellation including child processes. They test technical boundaries, not immunity
of model reasoning to every prompt injection. They do not validate a different CI
image or resolve package-advisory findings.

### Real conversation and provenance

A real native conversation answered how confirmation and uncertain-publication
reconciliation work, with repository paths, line references and the frozen commit.
Its answer explicitly distinguishes inspected implementation from tests not run and
real deployment behavior not proved by source inspection. Closing and reopening the
browser preserved the response. No independent analysis was created by discussion.

For a deliberately unanswerable question about a named human security approver, the
model reported no such attestation in the inspected sources. It distinguished the
date of an agent-assisted review from human production approval and did not invent
a person or approval date. The native session was resumed for the second exchange.

The source-disclosure endpoint resolves ten cited files at the frozen commit. Its
structured entries currently return file-start previews without precise line ranges
for this answer, despite prose citations containing line numbers. Treat these as
file-level disclosure, not independently captured exact-passage receipts.

### Remote checks remain distinct

The current [Checks run](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42172040940)
reports **1,698 passed and three failed** backend tests: a lazy-skills capability
assertion and two evaluation cases requiring an unavailable `rg` executable. Its
frontend browser campaign reached the 20-minute job limit. The current
[Security campaign](https://github.com/ThibautSchmitt/SpecHelper/actions/runs/42172040710)
passes source/security dependency gates, but remains unsuccessful overall because
image/runtime/DAST gates fail. Local passes do not override these failures.

The deep-analysis preparation selected only the Docker-related user exchange and
its assistant reply (two of the conversation exchanges). The frozen cycle marks
the user text as `user_statement` and assistant text as unverified context, not
technical evidence. The baseline and explicitly edited need are retained.

The live conversation renders at 375, 768 and 1,440 pixels without horizontal
document overflow or observed page JavaScript errors. Screenshots have no committed
comparison baseline; visual regression is inconclusive. No complete accessibility
or Core Web Vitals assessment is claimed.

The Analyst requested a single clarification about supported architectures and
existing durable artifact storage. The conversation changed to `AWAITING_REPLY`
without a technical error. The test requirement was narrowed to Linux/amd64 and
no new internal storage service; uncertain trust/availability decisions must remain
explicit. This answer defines requirements, not observed infrastructure facts.
The first actual analysis job ran for over six minutes without the former
five-minute supervisor termination.
The clarification was submitted through the actual answer form. Execution resumed
in the same analysis cycle, retaining the completed observations.

A separate source spot check of three prose citations matches the frozen source: the
confirmation control, the reconciliation-without-recreation branch and publication
uniqueness constraints. This does not validate every model interpretation or fix
the structured passage-disclosure limitation above.
The Counter-analyst starts in a distinct context. The run records the expected
`LIMITED_DIVERSITY` warning because all authorized roles use the same model family.
Separate sessions are not described as provider diversity.

The Counter-analyst requested a further trust-bootstrap clarification instead of
inventing an installed verifier. The answer explicitly leaves an authenticated
artifact and verifier choice unresolved, permits a partial conclusion and rejects
claims of full-image reproducibility or permanent upstream availability.
The completed Counter-analyst output retains the open investigations and identifies
a concrete version-check weakness: the current shell pattern accepts a version
string beginning with `gh version 2.103.2`, including a longer matching prefix.
An additional source inspection confirmed the pattern in `scripts/security/image-probe.sh`.
This finding is not a claim that the wrong package is actually installed.
The persisted native session IDs differ between discussion, Analyst and
Counter-analyst calls. The run retains both clarifications and the original Git SHA.
The Validator starts with another independent context.
The completed Validator review contains supported claims tied to frozen file/line/
excerpt references and explicitly states static-inspection limits. It distinguishes
the SHA-256 of the keyring file from an OpenPGP fingerprint and leaves the current
artifact availability, verifier bootstrap and complete-image reproducibility open.
Source inspection is not represented as an executed image build or a live
upstream check. The completed run is explicitly `PARTIAL`, and the conversation
returns to `DISCUSSION`, with all required role steps finished.

A remaining presentation/quality issue is that the accumulated business-summary
uncertainty list still includes old architecture/storage questions after the
Linux/amd64 clarification, alongside duplicated limitations. Do not interpret all
entries in that aggregate list as unresolved current questions. The current trust/
artifact availability limitation remains real.

### Draft and selected documents

The real conversation-native writer produced one active draft about the Docker/gh
need, linked to the partial analysis. It did not use the last clarification as a
standalone ticket subject or merge the earlier publication/approval questions into
the ticket. The draft remains `ticket_verified: false` and explicitly says that
acceptance tests still need to be run after implementation.

A real edit/save/close/reopen journey preserves the manual edit and the same draft
ID. The Save action remains in the viewport at 375 pixels. No page JavaScript error
was observed. Preparing the draft did not create a second analysis cycle.
The three selected documents were queued in one real writing operation only after
choosing the existing authorized GitLab test destination and requesting publication
preparation. No external publication started. A missing French translation for
`Optional` was corrected to `Facultatif` (English fallback entry retained). The
production frontend build, including TypeScript, passes. Only the frontend was
recreated for this correction; backend, worker and native runtime IDs/start times
were verified unchanged, and the health endpoint remains healthy.

All three files completed in the same generation job: `goal.md`, the business
report and the technical report. Their source-ticket snapshot equals the final
manually edited draft, they retain the original baseline and each remains
`verified: false`. The goal is structured around scope, implementation work, impacts,
acceptance checks and open investigations; it is not a raw conversation export.
The business report excludes the earlier abandoned storage proposal.

Reopening publication preparation reuses the generated files and reaches the
explicit unverified-publication confirmation. That confirmation was cancelled.
At that point, external creation and file transfer remained pending explicit user
confirmation. The subsequently authorized completion is recorded below.

### Authorized publication completion and recovery

After explicit user confirmation, GitLab accepted the issue creation with HTTP 201,
but SpecHelper kept the result `UNCERTAIN`: the configured Docker transport host
differed from GitLab's returned browser host, and GitLab returned its native
`/-/work_items/1` route rather than the older issues route. A read using the original
correlation reference found the existing issue in `test/test`; no new issue was sent.

The correction reuses the existing container-only localhost/Docker alias mapping
for origin validation in provider responses, confirmation storage and saved links.
Scheme, port, credential and unrelated-host restrictions remain enforced. Published
GitLab links additionally accept the numeric native work-item route, as documented
in the [GitLab CLI reference](https://docs.gitlab.com/cli/work-items/update/), while
redirect/search routes and query-bearing links remain rejected.

Focused provider/publication tests pass **134 cases with one skipped**. Related
history/HTTP/annex/document/active-draft tests pass **27 cases with one skipped**;
Ruff passes. The skipped cases remain unvalidated in this local campaign and are not claimed
as passes. No dependency or schema change was introduced.

After backup, the backend and worker source overlays were deployed. Hashes of
sessions, frozen result references, the active draft and the publication record
match before and after deployment; the native runtime container was unchanged.
This is not a clean dependency-image rebuild or a green overall release campaign.

The normal verification action reconciled the **same publication record and
idempotency key** to GitLab issue `test/test#1` (external ID 2). Recovery performed a
search and attachment transfers, not another issue-creation request. All selected
files (`goal.md`, `rapport-metier.md`, `rapport-technique.md`) report `TRANSFERRED`.
An independent GitLab API read verifies one issue matching the correlation reference
and one attachment note per file. The initial uncertainty remains in attempt history.

The active draft is released. Exactly one permanent publication message remains
after browser reload, and the same direct native link appears in Tickets published.
Following it reaches the correct local GitLab origin; a fresh unauthenticated
browser is redirected to GitLab sign-in, rather than being granted access implicitly.
No duplicate issue or duplicate publication message was created.
