# v1.4 delivery

## Preserved foundation

Keep the shared instance, FIFO worker, read-only analysis runtime, immutable
request baselines and result versions, ticket publication, English/French interface
and generated-content language. No new developer agent, graph engine, configurable
roles or environment instructions are introduced.

## Delivery and acceptance gates

| Area | Required behavior | Evidence required |
|---|---|---|
| Git sources | Multiple named GitHub/GitLab accounts and instances; paginated projects/branches, forks and stable remote identities | Provider contract tests including two GitLab instances, masked credentials and permission errors |
| Environments | Connection → repository → branch rows, mixed providers/forks, duplicate detection and change preview | Browser checks and server validation; local Git synchronization and pinned historical SHA checks |
| Git storage | One mirror per remote, isolated environment/generation worktrees, no fork substitution | Actual local repositories with divergent branches and parent/fork content |
| AI configurations | Named terminal configurations, model, identity sharing, activation, default/preference and bounded fallback | Three configurations including two of one provider; identity-isolated runtime checks |
| Availability | Known exhaustion excludes the underlying account; absent session/weekly telemetry stays unknown | Scheduler and typed observation tests; no invented percentages or resets |
| Visibility | Sidebar connections/source summary; actual queue assignment and per-step audit | Desktop/mobile checks, queued unassigned state, immutable execution snapshots |
| Preservation | Deletion/expiry cannot cascade into tickets, requests or history | Migration, protected deletion and historical artifact checks |

## Integration gates

Run focused tests before integration, then the complete relevant backend and browser
suites, build/type checks, lint, migration consistency and Linux runtime smoke checks.
Rehearse migration against a restored local database and compare historical data
before deploying. Keep provider-contract fixtures distinct from actual account
tests; no external publication is authorized by an analysis.
