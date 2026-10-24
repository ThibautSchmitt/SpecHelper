> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v2.0 acceptance review

Review date: 2026-10-23. Scope: portable declarative agents/skills, environment
selection, provider model metadata, cumulative public roles and historical
configuration. Existing read-only and shared-team security boundaries remain in
force. Conversational library generation, source changes, privileged scripts and
production Copilot execution are outside this release.

## Requirement evidence

| ID | Requirement | Implementation and verification |
| --- | --- | --- |
| 20-01 | Global agent/skill library with protected versioned CRUD | Shared definitions, immutable revision/audit records, optimistic expected-version checks, activation and archive-after-disable. Required workflow/dependency/environment references block deletion. API and browser tests cover creation, editing, stale edits, audit and retained historical versions. |
| 20-02 | Environment assignments without duplicated definitions | Environments store null-or-list references and an independent revision. Draft preview does not persist changes. Execution snapshots retain the chosen full versions separately from configuration references; migration/data-preservation and environment-selection tests pass. |
| 20-03 | Provider adaptation and explicit incompatibility | Codex/Claude retain their native schemas, sessions and runtime transport. Declarative provider/capability requirements are checked before inference; unavailable required skills or conflicting overrides stop explicitly. Preview includes agent/skill versions, adapter, role and connection instructions. No alternate privileged tool exists. |
| 20-04 | Selectable supported models and bounded availability tests | Catalog entries come from adapter metadata or explicit administration, never an invented list. Native installed Codex model-list returned eight entries offline without credentials or inference. Metadata support is separate from actual account access; unavailable discovery remains explicit for Claude. New selections require enabled catalog entries; legacy identifiers remain unverified. |
| 20-05 | Multiple connections and honest shared quotas | Existing named connection CRUD, independent identities, reliable matching-account grouping, shared capacity and session/weekly observations remain covered by the full backend/browser regression. Unknown windows and refresh errors are shown without estimated percentages or resets. |
| 20-06 | Cumulative Analyst/Counter-analyst/Verifier roles | Connections retain multiple simultaneous role permissions. Each role receives an independent working context; historical connection/model/provider snapshots remain unchanged. Existing role and session tests pass. |
| 20-07 | Prefer two-family A→B→A and three-family A→B→C | Actual model-family metadata takes precedence over provider defaults. Tests cover three explicit catalog families, two-provider alternation, same-family independent sessions, administrator waiting policy and strict role eligibility. Disabled catalog models are excluded from scheduling. |
| 20-08 | Connection/provider/model/role in queue and history | Compact cards retain connection/role/provider artwork and now show the actual model inline. Step history preserves execution snapshots, provider changes and diagnostic/fallback warnings. Browser tests cover live/unassigned/previous assignments and historical renames. |
| 20-09 | Custom instructions cannot change permissions or obtain secrets | Schemas reject executable/tool/permission fields and unsupported capabilities. Known configured credentials are rejected in definition fields. A custom instruction remains prompt text inside unchanged UID/capability/seccomp/mount/network restrictions. Current-source Linux probes again deny source writes, credential/socket/other-session access and arbitrary egress, including four indirect-content carriers. |

## Validation results

- Full backend run: **536 passed, 1 skipped**; the Linux-only host skip is covered
  by the actual container probe. Subsequent focused checks cover the additional
  runtime catalog authentication case and final credential-field validation.
- Full browser run: 137 passed, one catalog-key convention failure. The diagnostic
  labels were corrected to use the project's English-key convention; all eight
  localization/model cases then passed. This covers all 138 cases across the full
  run and focused re-tests, rather than claiming a single clean full-suite run.
- The eight new library/environment workflows cover EN/FR, desktop/mobile and
  light/dark themes. Screenshots were inspected; narrow action/field overflow found
  during development was corrected and re-tested.
- Two additional browser cases exercise creation, editing, deactivation, archival
  and retained revisions against the actual isolated API on desktop/mobile.
  The existing historical-context cases now also verify the frozen library text
  and version when switching between old and current results.
- Production frontend build, TypeScript and Ruff checks pass. Migration drift check
  reports no changes. Migrations 0023/0024 applied to a protected database copy;
  all original column values in **30 tables and 384 rows** were preserved.
- The production frontend also passes the 16 access/library/model browser cases
  used by CI; final model editing and historical library rendering were re-tested
  separately against the production build.
- An actual-orchestrator test with controlled provider responses edits, disables
  and archives a skill during execution: all five calls retain its original version. Published
  results and original library snapshots remain unchanged.
- Current-source Linux probe reports UID/GID 10001, zero capabilities, seccomp,
  read-only sources, hidden credentials and other sessions, provider-only access,
  four audited destination denials and confined PDF parsing.
- Model discovery is metadata-only. Native Codex list output proves the installed
  protocol works, not subscription entitlement; no paid inference or real Copilot
  account validation was performed.
- Candidate Gitleaks scan reports no secrets. Semgrep covers 149 production files
  with six local rules, no findings and no parse errors; new library/model/runtime
  and interface files were explicitly verified in the scanned-path inventory.

## Explicit limits

The [model/library guide](../guides/ai-library.md) distinguishes unverified, metadata-supported
and actually available models. Claude has no validated non-inference discovery in
this integration. Manual family declarations must match documented underlying
families. Editing-session audit is pseudonymous, not per-user authentication.

The [Copilot evaluation](../guides/copilot-evaluation.md) records official platform surfaces
and outstanding target-environment checks. Copilot remains experimental and rejected
as an execution provider. Existing [v1.9 security conditions](acceptance-v1.9.md)
still apply; this feature release does not certify another host or deploy the
shared instance automatically.
