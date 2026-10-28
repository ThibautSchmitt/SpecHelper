# Native provider metadata and publication authorization

This document records the v2.9.1 implementation and verification boundary. A
catalogue entry means native CLI support, not confirmed account access. Only an
actual successful analysis establishes the stronger access observation.

## Native verification on 2026-10-27

| Provider | Installed CLI | Metadata read actually exercised | Quota evidence | Access boundary |
| --- | --- | --- | --- | --- |
| ChatGPT / Codex | 0.163.0 | app-server `initialize`, `model/list`, `account/rateLimits/read` against the connected identity | Separate 300-minute and weekly windows, remaining percentages and explicit reset timestamps | Eight returned models and their native model-specific effort arrays; no analysis turn submitted |
| Claude Code | 2.1.309 | Stream-JSON SDK `initialize` control request in an isolated home, with no user message | No supported standalone account quota reader verified; display Not reported | Installed CLI returned structured model/effort metadata without authentication; no Claude account was connected, so authenticated discovery/access remains untested |
| Antigravity | 1.4.7 | `agy models`, then `agy -p /effort --output-format json --model <returned-model>` against the connected Google identity | Native standalone `agy -p /usage --output-format json`: separate Gemini and Claude/GPT weekly pools with exact resets | Six returned models; tested model returned low/medium/high, zero turns and zero token usage; no generated analysis submitted |

Native Codex observations at approximately 10:22 UTC were 86% remaining for the
short window and 38% for the weekly window. Resets were supplied by the provider
as 2026-10-27 15:11:53 UTC and 2026-11-02 06:15:05 UTC. These are dated verification
observations, not current quota promises or fixture values used in the product.

Codex `app-server generate-json-schema` was also exercised without authentication
or inference. Its installed `CreditsSnapshot.balance` is a nullable string; the
adapter accepts finite decimal balances as credit units, never percentages. This
was regression-tested against the schema; no positive real account credit balance
was required or claimed in the native quota observation above.

Correction after direct verification: the pinned Antigravity CLI supports standalone
`agy -p /usage --output-format json` even though help has no `usage` subcommand.
The returned `command.name=usage` payload exposes typed quota groups/buckets,
`remaining_fraction` and `reset_time`; it reports zero turns and zero token usage.
The adapter uses this built-in command, never an ordinary generated usage prompt
or an interactive terminal scrape. On 2026-10-27 the connected identity reported
Gemini at 0% until 2026-11-01 08:15:41 UTC, and Claude/GPT at approximately 4.78%
until 2026-11-02 11:26:51 UTC. These are dated observations, not current guarantees.
Groups retain separate scope; Gemini exhaustion cannot block Claude/GPT. Unknown
future buckets remain provider-scoped rather than being guessed account limits.
Read failures retain previous observations. Normal locked credential rotation is
preserved, and no API-key fallback or generation is introduced.

The Claude SDK initialization protocol was verified without a user turn, but its
catalogue can be bundled even without authentication. SpecHelper requires a
connected identity before using this adapter and labels the result Supported,
never Available merely because initialization succeeded. No Claude quota or
paid-account entitlement has been inferred from this result.

## Refresh and preservation rules

- Each observed window retains its own percentage or credit units, duration,
  reset time, observation time, source and scope. Missing values stay missing.
- Account limits and provider/model buckets are distinct; a model limit does not
  automatically exhaust the entire account.
- Connection/reconnection, completed invocations (including errors), manual reads
  and known reset deadlines trigger native metadata refresh. Runtime outages
  retain old observations rather than manufacturing a successful refresh.
- Shared identity row locks and throttling coordinate browser reads. Invocation
  metadata persistence preserves BUSY leases and existing scheduler decisions.
- The sidebar summarizes the most restrictive quantified account window. Settings
  lists all windows. Failed reads retain observations with a stale warning.
- The last validated model catalogue survives read failures. Unsupported effort
  choices are rejected server-side as well as omitted from the selector. Old
  configurations and historical sessions retain their original values.

Primary protocol references:
[Codex app-server](https://learn.chatgpt.com/docs/app-server),
[catalogue versus entitlement](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server),
[Claude SDK initialize implementation](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py),
[Antigravity effort](https://www.agy.dev/docs/cli/commands/effort/),
[Antigravity usage](https://www.agy.dev/docs/cli/commands/usage/).

## Publication OAuth options

The existing publication adapters were inspected separately from Git-source
authentication. They currently accept dedicated manual credentials. No publication
OAuth application, callback handler, refresh-token lifecycle or browser flow has
been added or functionally tested in this change. The UI states this limitation;
it does not show a button that merely opens a provider website.

| Platform | Native browser option reviewed | Required integration before offering a working button | Current verified scope |
| --- | --- | --- | --- |
| GitHub Issues | GitHub App preferred for repository-scoped Issues permissions; OAuth alternative | Registered application, installation/account authorization, dedicated publication credential and renewal/revocation | Existing dedicated-token adapter contract tests; source GitHub login is separate and cannot authorize publication |
| GitLab Issues | OAuth2 authorization code on the configured cloud/private instance | Application registration on that host, exact redirect URI, appropriate issue access, token refresh/revocation | Existing private-instance-aware token adapter contract tests |
| Jira Cloud | OAuth2 3LO | Registered Atlassian integration, consent, accessible site selection, API gateway/site identifier, rotating refresh tokens | Existing REST v3 account-email/API-token adapter contract tests; 3LO gateway transport remains unimplemented |
| GLPI 11 | High-level API v2 OAuth2 authorization code | Registered OAuth client, server grant/scopes, callback, expiry and refresh handling, API v2 adapter | Existing legacy `apirest.php` adapter tests; no API v2 OAuth compatibility is claimed |

A future implementation must bind single-use, expiring anti-CSRF state to the
current authenticated administration session, platform, host and target connector.
It must validate exact callback and provider URLs using existing network rules,
encrypt token material, serialize rotating refreshes, support revocation and keep
source-read credentials separate. The final human publication confirmation and
environment/destination permission checks must remain mandatory.

Provider documentation reviewed:
[GitHub Apps and OAuth differences](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/differences-between-github-apps-and-oauth-apps),
[GitLab OAuth provider](https://docs.gitlab.com/integration/oauth_provider/),
[Jira Cloud OAuth2 3LO](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/),
[GLPI high-level API authentication](https://help.glpi-project.org/documentation/modules/configuration/general/api/restful-api-v2).

No real external issue publication or OAuth authorization was performed for this
verification. Contract tests do not establish live permissions or tenant access.
