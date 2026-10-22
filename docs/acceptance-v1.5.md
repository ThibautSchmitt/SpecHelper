# v1.5 acceptance report

Verification date: 2026-10-22.

## Requirement coverage

| Requirement | Implementation and evidence |
|---|---|
| Exactly one comparison pair | Confrontation executes analyst, autonomous counter-analysis, comparison and optional verifier. More configured connections do not create more analyses. Tests assert the exact invocation sequence. |
| Consecutive family diversity | Live role assignment prefers A → B → A and an unused third family when eligible. Same-family execution requires policy permission and records a warning; restricted roles and unavailable families produce explicit waiting. Accounts and model display names cannot fabricate diversity. |
| Independent sessions | Role contexts use separate writable mounts even when a context UUID equals the request UUID. Actual Linux checks verify six contexts and twelve calls across both terminal adapters, with private notes, history and temporary files isolated. Sources and attachments remain read-only and share the same SHA. |
| Autonomous counter-analysis | Its first prompt contains the business dossier and baseline without the analyst's current conclusions. Only the subsequent comparison receives both structured reports. Tests inspect prompt boundaries and the runtime verifies filesystem isolation. |
| Configurable administration | Global instructions, active internal functions, default skills, verifier/fallback policy and bounded limits persist. Cumulative connection roles, additional instructions and sparse skill overrides affect actual prompts. Required functions remain available; settings cannot grant technical write rights. |
| Bounded verification | At most one focused check runs. Durable invocation counts and deadlines bound provider fallback and waiting. Explicit unresolved verification points are retained in ticket risks and full goal constraints with PARTIAL status. Invalid final formatting cannot publish. |
| Recovery and history | Checkpoints preserve validated outputs across unavailable-role waits. Only the failed stage is reassigned. Clarification starts fresh role contexts, reuses safe business/attachment facts and reassesses source conclusions. Published artifacts remain immutable. |
| User visibility | The queue exposes current role, connection/model and warnings. Request details show role steps, family attribution, verifiable conclusions and fallback/diversity warnings. Warning-bearing history opens automatically. |

## Validation

- **322 backend tests pass** on disposable PostgreSQL 17, including new role/family
  selection, instructions, checkpoints, limits, uncertainty preservation, migration
  and isolated-runtime cases, plus existing source/ticket/database workflows.
- **58 browser scenarios pass** on desktop and mobile. English/French catalogs have
  matching keys and placeholders. Existing requests, ticket publication, named source
  and assistant settings remain covered alongside AI & Agents configuration.
- Production frontend build and TypeScript checks pass. Ruff, migration consistency
  and Docker Compose validation pass.
- Actual Linux deterministic workflows pass for dual-provider confrontation,
  single-family confrontation with a warning, verifier-disabled comparison and
  ordinary analysis. Clarification, session resumption and two immutable artifact
  versions are checked. These fixtures do not measure live model quality.
- A restored application database migrates with all thirteen checked historical
  fingerprints unchanged, covering requests, versions, artifacts, messages, sessions,
  environments, Git metadata, database connections and publications.

## Boundaries

Production terminal adapters remain Codex/OpenAI and Claude/Anthropic. The rule for
three distinct families is verified with a controlled future-provider selection
fixture; this does not claim a third installed runtime adapter. Provider permissions,
subscription models and quota telemetry remain subject to the actual account.

Verifier output is an AI evidence check, not human business approval. People must
review the ticket and goal.md. External ticket publication retains its separate
human confirmation. No private reasoning, unbounded debate, voting panel, source
writes, business database writes, developer agent or PR action is introduced.

See [role operation and settings](orchestration.md) and
[existing connection behavior](connections.md).
