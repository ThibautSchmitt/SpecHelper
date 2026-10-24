# Settings and provider usage

The bottom-left Settings button opens three tabs. Main navigation contains only
Requests, Questions and Tickets.

| Tab | Configuration |
| --- | --- |
| General | Browser theme; shared instance name, short label, language, color and global instructions |
| AI & Agents | Connections and their specific instructions, models, allowed roles, account usage and global skills |
| Environments | Git connections, read-only databases, environment repositories/branches/context and ticket connectors |

Connection actions use labeled icons with tooltips: refresh status/quotas, edit,
enable/disable and delete. Deletion still requires confirmation and is rejected
when analysis history requires retaining a connection.

## Account quota observations

Select **Refresh status and quotas** on an idle AI connection. Authentication checks
and quota reads do not submit a business request or send an inference probe.

Codex uses the installed official app-server `account/rateLimits/read` method in
a clean credential home. It does not create a thread or turn. Only observed
session/weekly percentages and reset times are displayed. The selected identity
and safe credential rotation are checked. The refresh has a bounded timeout;
provider response bodies are never shown as diagnostics.

The installed Claude Code CLI does not provide a supported standalone account
quota read. Its quota is explicitly unavailable; the interface links to the
provider's usage page. This does not prevent ordinary authenticated analysis.
A newer SDK's experimental `/usage` API does not establish support in this CLI.
See the official [Claude usage documentation](https://code.claude.com/docs/en/costs)
and [SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript).

**Last observed** dates the last actual snapshot. **Last checked** dates the latest
explicit refresh attempt. Failed or unsupported refreshes retain last-known
observations and do not turn them into current data. Unknown quota never means
unlimited capacity. Authentication success alone does not clear known quota
exhaustion; provider permission or the normal scheduler's recovery remains required.
Configurations sharing an authentication identity share quota observations.
The sidebar shows the limiting observed remaining percentage: green at60–100%,
orange at20–<60% and red below20%. Unknown and authentication-required states have
no invented bar. Last observations and stale states remain visible offline. Visible
tabs refresh metadata every120seconds; a shared identity lock/throttle coordinates
multiple browsers, and busy analyses are not probed.

## Instructions and skills

Set shared instructions in General and specific instructions on each AI connection.
Security rules and the mandatory role mission take priority. Environments retain
business terminology, factual context, source repositories and documents; they do
not introduce a third configurable instruction level.

The global library exposes active compatible skills without role, connection or
environment assignments. Assistants select relevant procedures and load full text
on demand. Current steps retain captured content and report actually loaded
versions; the discovery registry alone does not prove loading. Migration notices
identify legacy content preserved for review rather than silently promoted.
Current skill editing does not ask business users to select compatible assistants or
tool permissions. Requirements are calculated metadata, checked against each step's
actual capabilities. The detected model catalogue is primary; manual additions
remain available through a secondary action.

There is no fixed analysis-duration setting. The interface shows observed elapsed
time and explicit AI/user waits. See [current orchestration](orchestration-v2.4.md).

## Environment ticket destinations

Each environment owns its connectors, credentials and allowed destinations. New
publication is checked against the request's environment on the server, including
retries. Existing ticket history is immutable. See [ticket publication](ticketing.md)
for migration, legacy assignment, recovery and deletion rules.
Environments also accept optional official reference URLs/domains with notes.
These are non-exclusive factual starting points, with no priority over role or security
rules. See [official references](official-references.md).

## Historical settings validation

The consolidated change passes 443 backend tests on disposable PostgreSQL 17 (one
Linux-only host test skipped), 118 desktop/mobile browser scenarios and six final
localization rechecks. Production build, TypeScript, Ruff and migration drift
checks pass. Four rendered light/dark cases cover 1440x1000 and 390x844; screenshots
and contrast/overflow observations remain private local evidence.

The local deployment was backed up before migration. All 16 historical model
fingerprints matched before and after it. A real non-inference Codex quota refresh
returned short-window and weekly percentages with reset timestamps through the
worker relay. This verifies usage retrieval, not real-model analysis quality.
