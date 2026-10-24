> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v2.5 acceptance evidence

Status: implementation and controlled integration checks passed.
Controlled responses establish application contracts and security boundaries, not
universal model correctness or live ticket-platform write guarantees.

## Requirement coverage

| Requirement | Implemented behavior | Evidence |
| --- | --- | --- |
| UX-01/02, AT-01 | Request/Question entry has environment, free text and optional files; no type selector | Real API defaults and EN/FR desktop/mobile form scenarios |
| UX-03 | Compact native file action, form drop, names/sizes/removal/errors | Browser keyboard/upload/validation/mobile layout checks |
| TK-01/02, AT-02 | Persistent project/standard format, real connector templates/types, editable suggestion and no-template fallback | Draft API and browser switching/reload scenarios; no analytical job created |
| TK-03, AT-03 | Native required fields remain authoritative across templates and standard format | GitHub Forms/Jira/GLPI metadata and server rejection checks |
| TK-04/05, AT-04 | Five-part concise standard, optional detailed business/technical sections, unchanged exhaustive goal | Deterministic EN/FR rendering, original artifact preservation and exact field preview |
| TK-06, AT-05 | Explicit file opt-in off by default, per-file selection and separate goal, named destination | API consent, ownership/MIME/size/hash/permission and browser checks |
| TK-07, AT-11 | Exact version/environment/SHA draft, optimistic revision, editable preview and stable publication reference | HTTP issue creation/lost response reconciliation; no blind repeated issue/upload POST |
| TK-08, AT-09 | Partial/unusable or missing independent checks remain visible but cannot publish | Backend provenance/role gate, browser disabled action and grouped partial card |
| WEB-01, AT-06 | Global conditional research instruction; Web tool absent in clarification/writing/demo | Persisted default policy and scoped invocation checks; no automatic fetch on hint save/tool creation |
| WEB-02 | Up to12 factual URL/domain hints and notes, non-exclusive and frozen | Revision/validation API, EN/FR settings and historical-context browser checks |
| WEB-03, AT-07 | Actual URL/title/consultation/hash receipts, effective date/version/jurisdiction/scope, explicit deployment distinction | Trusted receipt validation, invented/tampered/undated citation downgrades and export/UI checks |
| WEB-04, AT-12 | Independent readers, untrusted text, pinned public HTTPS, bounded redirects/transfers, no credential forwarding | DNS/mixed-address/redirect/transfer tests, actual Linux sandbox probe and script-shaped browser excerpt |
| UI-01 | Bundled provider marks with visible text and licensed generic platform fallbacks | EN/FR light/dark screenshots and artwork notices |
| UI-02 | Sidebar no longer polls or displays Git statuses; diagnostics remain in Settings | Browser source/sidebar checks |
| UI-03/04, AT-08 | Limiting observed remaining quota, exact colors, unknown/auth/exhausted/stale, metadata-only refresh | Percentage boundary tests;120s shared-identity PostgreSQL lock/throttle and periodic browser checks |
| QUEUE-01/02/03, AT-09 | Latest business-item card, grouped roles, completed collapsed, successful sync hidden, execution/result states separate | Queue API and desktop/mobile current/history/parallel/retry scenarios; lazy environment synchronization diagnostic |
| ADM-01, AT-10 | Active skills globally discoverable; calculated capability metadata; no manual provider assignments | Cross-provider revision/preview tests and manual/assisted editor browsers |
| ADM-02/03 | Detected models first, manual add secondary, two instruction levels and factual environments | Administration browser regressions and preserved v2.4 instruction/history tests |

## Observed validation

- Ticket backend:141 focused PostgreSQL checks, including18 new v2.5 scenarios,
  passed before the final exact-whitespace HTTP follow-up.
- User-facing forms/publication/queue:134 distinct browser scenarios have passing
  observations across the combined run and targeted corrections; final publication/form
  follow-up54/54 passed. Administration20/20 passed. Official-reference UI24/24 passed.
  Synchronization diagnostics8/8 passed, for186 distinct browser scenarios overall.
  These use controlled API fixtures in English/French on desktop/mobile and light/dark.
- Root Web/evidence/queue/skill/scheduler/omission integration:50 focused checks passed.
- The production frontend build and TypeScript passed; Ruff passed.
- The final full backend run passed **786 tests**, with one existing host capability
  skip, in200.85seconds. Missing material verification cannot hide behind READY,
  and more than fifteen AI-waiting items remain visible despite completed history.
  The subsequent read-only synchronization diagnostic passed **7 focused API/queue
  checks**, including two new endpoint cases: scoped/bounded/redacted history,
  unknown-environment rejection and no Job mutation.
- Gitleaks found no candidate secrets. Six Semgrep rules scanned194 production
  files with zero findings or parse errors. Locale key/source-value parity passed.
  Compose configuration, migration-generation consistency and backend/worker/runtime
  image builds passed; actual migration tests use disposable PostgreSQL.
- Real Linux `runtime.v25_smoke` passed with controlled public-page transport and no
  external network: actual sandbox-to-broker access, untrusted text, private/unsafe
  destination denial, caller-header rejection, no exposed credentials and readonly sources.
- Real Linux `runtime.v24_smoke` passed parallel sandbox/session/source/attachment
  separation, lazy read audit, authorized Git history with unrelated caches hidden,
  exact-attempt process-tree cancellation and idempotence in the new image.
- A separate real public HTTPS read of the official Python HTTP-client documentation
  succeeded on2026-10-24 and produced a title, consultation timestamp and content hash.
  The returned bounded text was explicitly truncated; this was not an AI interpretation test.

## Boundaries

External issue/file writes are verified with controlled HTTP transports, including a
real local HTTP server for lost responses. No native ticket-platform write is claimed.
Public-page contents do not grant capabilities; the reader is not semantic data-loss
prevention and has no universal official-site format support. Fetched provenance does
not certify legal applicability or model interpretation. See [official references](../guides/official-references.md).

No v2.5 shared-instance deployment, Git commit or push is implied by these checks.
The separately requested native v2.3 quality/token comparison is recorded in its own
[acceptance report](acceptance-v2.3.md), with actual provider observations only.
