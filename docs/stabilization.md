# Stabilization review

Review date: 6 November 2026. Inspected baseline: `c3b3b7a` and the accompanying
stabilization changes. This is an engineering review of available evidence, not
certification of model accuracy or deployment security.

**A stable-release recommendation is withheld.** Existing conversations, independent
analyses and confirmed publication are a coherent scope. The remaining work is
reliability and release validation, rather than additional product modules.

## Acceptance checklist

| Area | Current evidence | Remaining gate |
| --- | --- | --- |
| Ticket creation and resumption | Native REST creation, explicit confirmation, destination validation, selected-document caching and uncertain-creation reconciliation have tests. | Reading and updating a published external ticket with conflict detection is not implemented. Resuming an internal draft or reconciling creation is not external-ticket updating. |
| Answer quality and provenance | Exact Git commit/blob/line/excerpt checks, retained SQL/document receipts, honest unverified states and separate role contexts are tested. | A reviewed run with real models on a real application, including deliberately unanswerable questions. Source matching and separate contexts do not prove an interpretation correct. |
| Git version consistency | Real local Git tests retain analysis A after synchronization to B. Later investigations in the same conversation can use B without rewriting A's baseline. | Repeat the workflow during a real synchronization and through publication/resumption; PostgreSQL race checks require the disposable database. |
| Sources and secrets | SQL validation, restrictive-role checks, redaction, broker restrictions, hostile Markdown and read-only bindings are covered by code and application tests. | Repeat database grant/row-lock tests and exact-image Linux isolation probes. The latest security image campaign is not green. |
| Long work and recovery | Checkpoint/fencing tests and corrected configured supervisor deadlines cover interrupted work and bounded attempts. | Restart real worker/runtime containers during synthetic work, then verify cancellation, quotas and checkpoint resumption. |
| Business journey | Browser tests and controlled HTTP provider fixtures cover conversation, draft, optional analysis, documents, confirmed publication and lost-response reconciliation. | A real authorized application and test destination, followed by external edits, code evolution and conflict-safe ticket updating. |

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

Docker's daemon and the deployed local HTTP endpoint did not respond during this
review. No existing service, native session or business database was restarted or
modified to work around this. Local Compose configuration rendering uses no daemon.

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
