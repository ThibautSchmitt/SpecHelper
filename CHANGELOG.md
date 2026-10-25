# Changelog

Entries describe source implementation, not automatic deployment or universal quality.
Detailed dated evidence remains in the [archive](docs/archive/README.md).

## Unreleased

### Antigravity provider (v2.7)

- Add Antigravity to existing AI connections, exact model discovery and role selection.
- Pin native Linux CLI 1.4.7 and verify its official binary checksums.
- Add official Google account authorization with encrypted native OAuth credentials
  and a separate optional Gemini API mode with explicit billing consent.
- Keep reusable credentials outside analysis children; no host account import or
  implicit paid fallback is used.
- Preserve fresh native conversations, global skills and the existing step scheduler.
- Retain permission grants/observations separately; refused or failed necessary tools
  cannot become complete results or publish external tickets.
- Add real-CLI sandbox probes with synthetic Gemini transport and EN/FR browser coverage.

An authorized Google-account probe executed the discovered Gemini 3.8 Flash (Low)
model with actual source/global-skill reads and structured output on 2026-10-25.
Controlled tests cover three-family orchestration; representative accuracy, live
three-account throughput, monetary cost and missing quota remain unproven.
See the [provider contract](docs/antigravity.md).

### Documentation consolidation (v2.6)

- Consolidate active product, architecture, configuration, analysis and operations guides.
- Shorten the README around business value and the checked installation path.
- Inventory and archive older documents; retain security conditions and open limitations.
- Add documentation link/anchor and shell-example checks and maintenance rules.
- Verify startup with clean application volumes isolated from the existing instance.
- No application behavior, security policy or provider changes.

## v2.5 - 2026-10-24

Free-text entry; compact attachments; persistent ticket drafts, actual templates/types,
concise format, exact previews and explicit per-file delivery; conditional public
references with receipts; clearer queue/completeness/diagnostics; portable skills,
detected models and observed quotas.

See the [v2.5 report](docs/archive/reports/acceptance-v2.5.md) for controlled validation
and live vendor-write limits.

## v2.4 - 2026-10-24

Persistent scheduling per compatible AI step, cross-request concurrency, shared-account
leases and sequential per-request checkpoints; cancellation/retry/recovery without a
fixed total business deadline; lazy global skills, two instruction levels and independent
omission discovery. See [v2.4 evidence](docs/archive/reports/acceptance-v2.4.md).

## v2.3 - 2026-10-24

Mandatory independent Analyst, Counter-analyst and Verifier; scoped Git/SQL evidence;
source/index evaluation. Native measurements completed, but exact-citation quality
failed, leaving production indexing disabled. See [limitations](docs/known-limitations.md)
and [v2.3 evidence](docs/archive/reports/acceptance-v2.3.md).

## v2.2 - 2026-10-24

Guided business choices, decision history, explicit contradiction review, targeted
reanalysis and human validation. See [v2.2 evidence](docs/archive/reports/acceptance-v2.2.md).

## v2.0-v2.1 - 2026-10-23

Versioned declarative library/model metadata, then conversational creation, inactive
drafts, explicit activation, sandbox demonstrations and import/restore.
Current global-skill rules supersede manual assignments.
See [v2.0](docs/archive/reports/acceptance-v2.0.md) and
[v2.1](docs/archive/reports/acceptance-v2.1.md).

## v1.9 - 2026-10-23

Shared access protection, encrypted credentials, isolated provider execution, input
hardening and executed security checks with residual findings.
Current conditions: [security validation](docs/security-testing.md);
dated evidence: [v1.9](docs/archive/reports/acceptance-v1.9.md).

## v1.0-v1.8 - 2026-10-20 to 2026-10-22

Initial requests, Git baselines, clarification, immutable results; English/French;
ticket connectors; multiple Git/AI configurations; environment documents; Questions
and handoff; appearance and task panel. The [archive index](docs/archive/README.md)
links every version. Older timeout, optional-role, type and assignment rules are
historical and superseded by active references.
