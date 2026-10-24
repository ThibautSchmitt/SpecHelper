> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v1.9 security acceptance review

Review date: 2026-10-23. This report covers the reference Compose deployment and
release candidate, using disposable services and protected copies of existing data.
It does not claim that an existing installation has already been upgraded.

The scope is shared-team access protection, safe inputs and artifacts, encrypted
credentials, read-only Git/database analysis, an isolated provider broker, and an
executed security campaign. Authenticated team members retain equal access.
Automatic code changes/PRs and per-user tenancy remain outside the established
read-only product scope; contradictory acceptance labels do not enable them.

## Requirement evidence

| ID | Requirement | Verified implementation and evidence |
| --- | --- | --- |
| 19-01 | Secrets encrypted at rest and absent from public output | Authenticated database encryption with a separate key; domain-separated CLI vault; bounded no-follow reads, atomic legacy sealing and private temporary files; response/export/log redaction and refresh/rotation tests. Rehearsals preserved decrypted bytes of two credential-store files and 27 legacy session copies. Source/history and image secret scans are release gates. |
| 19-02 | Server validation and XSS/CSRF/access protection | Shared-password middleware runs before business-resource lookup; opaque expiring/revocable sessions, exact Host/Origin checks, CSRF and database-backed frequency/concurrency limits. Tests cover anonymous IDs, access boundaries, hostile origins and safe Markdown without executable HTML or remote images. |
| 19-03 | Dangerous attachments rejected or confined | Actual signatures, extension/type checks, streamed size/count limits, bounded DOCX ZIP expansion, executable/macro rejection, random immutable storage and safe downloads. Hostile-file regression and real PDF parsing in the constrained Linux child pass. |
| 19-04 | No repository or other-session writes | Exact runtime probe requires UID/GID 10001, zero capabilities, no-new-privileges, seccomp and isolated namespaces. Source writes fail and other sessions are hidden. Isolation failure aborts execution. |
| 19-05 | No Git credentials or push capability in child | Real OAuth stays in the supervisor; children receive per-run broker capabilities. Credential paths/sockets are hidden and arbitrary network access fails. Controlled native Codex/Claude protocol tests reach only allowed provider endpoints and classify an upstream 401 as an authentication error. |
| 19-06 | Git synchronization independent of agent permissions | Git regression creates repositories, mirrors and independent branch worktrees, fetches a new commit and preserves the frozen analysis baseline and files. Clone/fetch/checkout remain trusted-service operations; agent source mounts are read-only. |
| 19-07 | Business database rejects writes and bounds reads | Disposable PostgreSQL tests verify reads, source-enforced write rejection even with client read-only mode disabled, owner/superuser/table/column/CREATE privilege refusal, and bounded rows. Read-only transactions and timeouts add defense in depth. |
| 19-08 | Detect credential/network exfiltration attempts | Fixed-category, content-free broker auditing records denied destinations. Linux probes deny secret/socket/other-session access and arbitrary network, including forbidden operations after README, PDF, ticket and database injection carriers. |
| 19-09 | HTTPS cookies/authentication; no anonymous Admin | A certificate-verified disposable TLS proxy confirms anonymous Admin refusal, Secure/HttpOnly/SameSite cookies, required CSRF, login rotation, hostile-Origin rejection, logout/replay refusal and cleartext authentication refusal. |
| 19-10 | Executed scans and tracked targeted review | Gitleaks, Semgrep, pip-audit, npm audit, Trivy infrastructure/images, authenticated ZAP baseline and bounded active scan executed. CI preserves these gates. The targeted ASVS/WSTG review records defects, corrections, re-tests and deployment limitations. |

## Executed validation

- Full backend suite: **510 passed, 1 skipped**. The host-only Linux namespace
  check is exercised separately inside the built runtime. The suite includes real
  PostgreSQL privilege and read-limit integration tests.
- Browser validation: 120 cases passed in the full run; eight outdated UI
  assertions were corrected for the card layout and dedicated publication token.
  All eight plus six access/XSS scenarios then passed on desktop/mobile. Four
  card-layout cases also passed in light/dark themes after integration.
- TypeScript/build, explicit CI Ruff configuration, Compose configuration and
  migration drift checks passed. Migration 0022 was applied to a protected copy of
  the existing database: all fields in 26 business models, 371 rows, were unchanged.
- Credential-store and legacy-session rehearsals verified encryption and identical
  decrypted bytes, unchanged backups and 5,706 unchanged other session files.
  Native Codex status recognized the copied encrypted account. These checks did
  not connect a new provider account or consume a paid analysis.
- Linux probes verify non-root identity, zero capabilities, seccomp mode 2, denied
  namespace/tracing operations, read-only sources, hidden credentials and other
  sessions, provider-only access, four audited broker denials and confined PDF
  parsing. The deterministic carrier harness proves permissions, not an LLM's
  prompt-injection resistance rate.
- Semgrep covered 140 production files with no findings or parse errors. Gitleaks,
  Python dependency audit and npm audit reported no findings; infrastructure scan
  has only the exact, documented runtime-supervisor exception.
- ZAP baseline: **57 passed, zero warnings/failures**. Bounded active scan:
  **106 passed, zero warnings/failures**. HTTPS assertions all passed. Targets
  contained fictional data, no real provider accounts and no existing application
  volumes; production was not active-scanned.

## Findings, conditions and deployment limits

See the [findings register](../../security-testing.md#findings-and-re-test-register),
[threat model](../../threat-model.md) and [targeted review](security-review-v1.9.md).
Outdated tooling, CLI dependencies, missing API/error-route CSP and initial SAST
coverage were corrected and re-tested. Existing GitHub ticket connectors that
relied on the repository account now require a dedicated publication credential.

Raw image reports retain 65 runtime, 50 backend and 43 frontend high/critical
distribution records. Sixteen individual, exact-package applicability reviews
expire on 2026-11-22 and require same-image control evidence; they do not describe
vulnerability-free images. No unreviewed blocking findings or image secrets remain.
New/fixable high or critical findings, changed packages, missing evidence and expired
reviews fail the gate. A bounded TIFF job-denial-of-service risk and an
UNKNOWN-severity Go/OpenPGP inventory finding remain explicitly recorded.

The trusted namespace supervisor still requires elevated container permissions;
the analysis child does not. Session-size monitoring is not an atomic filesystem
quota. Administrators must preserve matching encryption/control-key backups and
review the actual host, TLS proxy and access configuration before broad exposure.
The targeted review is agent-assisted, not an independent professional human
pentest or certification. No absolute security guarantee is made.
