# v1.4 acceptance report

Verification date: 2026-10-22.

## Requirements and evidence

| Requirement | Implementation and verification |
|---|---|
| Multiple Git connections | Named GitHub/GitLab connections with independent encrypted secrets, server URL, activation, connection test and paginated discovery. Two independent local HTTP GitLab fixtures verify authentication, projects, forks and branches alongside GitHub contract coverage. |
| Flexible environments | Connection → repository → branch rows support mixed providers and forks. Browser scenarios verify dependent selections, search, pagination, duplicate rejection and edit preview. Server checks the selected remote and branch. |
| Stable sources | Provider, instance and remote ID identify a mirror across accounts. Actual local Git repositories verify mixed GitHub/GitLab/fork content, distinct branches, retained old commits and immutable request workspaces. Two branches of one remote keep separate worktrees and share a mirror lock. |
| Connection incidents | Authentication errors mark synchronization failures without deleting environments. Referenced connection deletion requires exact-name confirmation and disables the connection. Completed authorization attempts retain audit rows while permitting deletion of unused connections. Cancellation cannot redirect credentials to another connection. |
| Multiple assistant configurations | Three named configurations, including two of one provider, can share an identity or use isolated authentication namespaces. Tests cover defaults, preference, activation, model propagation, model rejection and bounded fallback. |
| Account quotas | Shared identities and reliably matching account fingerprints share quota/capacity. Missing windows stay unknown. Known exhaustion excludes the account; authentication health cannot reset it. Tests cover session/weekly observations and official reset timestamps. |
| Execution visibility | Sidebar lists configured assistants and source-provider status. Queue cards expose actual assignment/model or no assignment before execution. Per-step snapshots preserve connection, provider, model and failures after configuration changes. Browser and backend checks cover these states. |
| Preservation | Migration tests retain request/version/artifact fields and credentials, import legacy authentications and advance automatic database sequences. A restored application database migrates with all nine checked historical fingerprints unchanged. |

## Validation

- **288 backend tests pass** on disposable PostgreSQL 17, including source discovery,
  actual Git worktrees, queue behavior, migrations, runtime credentials, quota
  parsing, ticket publication and read-only business database access.
- **52 browser scenarios pass** on desktop and mobile, covering both languages,
  existing request workflows, ticket publication, new source/assistant configuration,
  delayed settings responses and historical attribution.
- A read-only check against the deployed application passes on desktop and mobile,
  including existing results, publication dialogs and named connection settings.
  The deployed migration preserves all nine checked historical fingerprints.
- Production frontend build and TypeScript checks pass. Ruff, migration consistency
  and Compose configuration checks pass.
- Linux namespace isolation passes: sources/history remain readable, writes are
  denied and unrelated credentials remain hidden. Deterministic Codex comparison
  and Claude continuation checks pass with real sandboxing and immutable exports.
  These fixtures do not measure model quality or authenticate real accounts.

## Telemetry and compatibility boundaries

Codex quota parsing reads optional official `token_count` / `rate_limits` snapshots
from the current invocation's rollout, bounded to its own session files. An explicit
window duration distinguishes session and weekly windows; percentages and resets
are never derived from unstructured error text. Missing output remains unknown.
Claude's final JSON result does not establish separate reliable session/weekly
windows; those indicators remain unknown. No costly quota probe is launched.

Source transports use GitHub.com and GitLab REST v4. Self-hosted behavior is verified
with controlled local HTTP services, not every GitLab server edition. Additional
real account authorizations depend on provider/CLI support and terms. Runtime
tests validate credential namespace isolation and selected CLI arguments; no claim
is made that every model is included in every subscription.

Existing analysis roles and comparison semantics remain unchanged. The application
adds no developer agent, mandatory graph/index engine, branch, commit or PR action.

See [connection behavior](connections.md) and [ticket publication](ticketing.md).
