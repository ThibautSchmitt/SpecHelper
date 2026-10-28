# Antigravity provider

The Antigravity adapter uses the native Google CLI within the existing isolated
runtime. [Analysis](analysis.md) remains the authority for mandatory roles, scheduling,
independent review and result completeness. This adapter adds no local models,
business filtering, diagrams or ticket-publication framework.

## Connect and select a model

Open **Settings → AI & Agents**, create an Antigravity connection and choose
**Connect with Antigravity → Continue with Google**. Use your Google account in
the official browser flow. If the official page supplies an authorization code,
paste it only into the connection dialog. Antigravity verifies account and region
eligibility; having a Google or Gemini account does not establish access by itself.
No API key is required for this account flow.

The native CLI signs in inside a fresh trusted home. Its consumer OAuth profile is
stored encrypted in the runtime vault. The application does not import the developer
OS keyring, browser cookies or ambient credentials. Account credentials never enter
an analysis child, prompt or the application database. ChatGPT/Codex and Claude
retain their existing subscription authorization flows.

**Use a Gemini API key** remains an explicit optional alternative for operators who
choose provider API billing. Its password field and billing confirmation are separate
from Google sign-in; account sign-in never falls back to this mode automatically.

Saving a credential confirms configuration, not subscription/model entitlement or a
successful inference. Refresh the connection's model catalogue, select an exact
returned identifier, and save it. Antigravity execution requires an explicit model;
there is no silent model substitution. A clean native metadata read observed fourteen
models in pinned CLI 1.4.7; the application does not seed that list.

Configurations sharing the same identity or entered API credential share local
capacity. Different keys can belong to the same Google project/account; they do not
prove independent upstream quota. Native OAuth profiles do not expose a guaranteed
stable account identifier: separate Google sign-ins are not proof of separate quota.
Connections sharing one SpecHelper identity retain a shared local capacity lease. Session/weekly percentages and reset times remain
unknown when no supported observation exists. The pinned CLI now exposes native
weekly group observations through `agy -p /usage --output-format json`, with zero
inference turns. Gemini and Claude/GPT limits remain separate. CLI-reported invocation usage is
retained only when present; it is not an account quota or monetary-cost estimate.
The native CLI may make auxiliary title-generation calls in addition to the selected
analysis model, so its final usage must not be assumed to cover every billed request.

## Native execution contract

The runtime installs Linux CLI 1.4.7 from exact official URLs and SHA-512 digests
in [the release manifest](../runtime/antigravity-release.json). The build verifies
the archive and installs only its regular binary member. The binary is read-only;
metadata checks reject a changed version or missing required flags before analysis.
Both Linux architectures are pinned; the local executed probe used amd64.

One invocation uses one fresh CLI home and conversation, including retries/repair.
It never implicitly resumes the last conversation or imports another request's state.
The invocation uses the documented single-turn stdin streaming protocol with JSON
schema output. This keeps request text out of process arguments. It deliberately
does not combine `-p` with streamed stdin: native documentation states that the
stream-input mode ignores a prompt passed through that flag.

The parser requires a consistent conversation, a valid terminal result and structured
output. Exit code zero or native SUCCESS alone is insufficient. Authentication,
quota, model selection, permission refusal, technical timeout and tool failures are
distinct observations. A usable output with unresolved tool/permission limitations
remains partial; a refusal without usable structured output is an explicit error.
Later roles cannot erase these limits or publish a READY label around them.

## Permissions and data boundaries

No `--dangerously-skip-permissions` option is used. Generated CLI settings grant a
bounded command list and reads of the mounted source, skill, context and attachment
aliases; writes are denied in native policy. Actual native mode/tool observations
and service-configured grants are retained separately as bounded audit metadata,
without raw tool arguments or outputs.

These settings do not replace enforcement. Bubblewrap mounts the authorized sources
and resources read-only, hides other sessions/credentials, and runs the CLI as UID/GID
10001 with zero capabilities and inherited syscall restrictions. The same per-run
broker enforces SQL and conditional public-reference access. The CLI sees an expiring
synthetic capability. In Google account mode, the trusted broker injects the real
OAuth access token only at the pinned native Cloud Code endpoint. Its allowlist
contains metadata and inference methods, with account mutations denied. Optional
API mode uses a separate fixed Google Gemini endpoint and API-key header. Arbitrary destinations, file uploads, extra query parameters
and redirects are denied.

Native model and tool events are evidence, not permission grants or proof of semantic
understanding. See the [threat model](threat-model.md) for provider transfers and
residual trusted-supervisor privileges.

## Verification boundaries

The full backend regression recorded 931 passing tests and one existing host-only
skip; subsequent focused checks cover Google URL wrapping and metadata failure categories. Twenty-four
English/French desktop/mobile browser scenarios verify current provider setup,
billing consent, secret-field clearing, unavailable runtime and partial results.

The [native Linux smoke](../runtime/v27_smoke.py) executes the pinned real CLI with
controlled Gemini HTTP responses and synthetic credentials. It verifies actual
source/skill reads, fresh conversations, a native SUCCESS envelope containing a
refusal, blocked source/SQL writes, denied arbitrary network access and exact-attempt
cancellation without stopping another native conversation. A rejected SQL statement
never reaches the database; PostgreSQL privilege checks have separate integration
evidence. Synthetic response usage fields are not live model measurements.

The [Google account smoke](../runtime/v27_oauth_smoke.py) also verifies the official
browser authorization URL, required OAuth/PKCE parameters after terminal wrapping,
exact login cancellation, actual raw-terminal code submission, explicit exchange
failures and native consumer-protocol inference with synthetic transport. The relay preserves the native endpoint and does not rewrite eligibility
responses. Optional account mutation, quota, administration and trajectory-sharing
calls remain denied inside the analysis child when they are not needed for inference.

On 2026-10-25, a separate authorized Google-account probe executed the discovered
`gemini-3.8-flash-low` model through the native CLI and trusted relay. It returned
the exact random markers from a scoped source file and a global skill, produced
the required structured output and a French finding, with no permission limits.
The skill read was retained in the service audit. No Gemini API key was used.

This establishes one real model/connection execution on Linux amd64. The full
three-family worker path has controlled-response integration coverage; this probe
does not establish representative business-analysis accuracy, simultaneous live
three-account throughput, monetary cost or missing quota telemetry.
See [known limitations](known-limitations.md).

## Official references

- [Installation](https://antigravity.google/docs/getting-started)
- [Authentication and explicit API mode](https://antigravity.google/docs/install?tab=cli)
- [Headless modes, schemas, events and soft refusals](https://antigravity.google/docs/cli/headless/)
- [Native permission matching](https://antigravity.google/docs/permissions)
