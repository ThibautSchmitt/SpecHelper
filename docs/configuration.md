# Configuration

Open **Settings** at the bottom left. All settings belong to the trusted shared
instance except the browser's appearance preference. Never paste credentials into
instructions, notes, attachments or documentation.

| Tab | Owns |
| --- | --- |
| General | Browser appearance, instance name/short label/color/language and global instructions |
| AI & Agents | Named assistants with native model/reasoning choices, eligible roles, connection instructions and global skills |
| Sources & environments | Separate Git sources, PostgreSQL connections and Environments tabs |
| Connectors | Publication connectors, still associated with their own environment |

## First setup

Connect a Git source and an eligible AI account, create an environment with its
repositories/branches, and wait for successful synchronization. Optionally add
read-only PostgreSQL and factual reference documents. Configure ticket connectors
in the Connectors section for each environment; [ticketing](ticketing.md) owns their destinations,
credentials, templates and recovery rules.

## Git sources

Use **Settings → Sources & environments → Git sources** to add named GitHub or GitLab connections. GitHub
supports its official browser authorization flow. GitLab.com and self-hosted
instances accept an appropriate read-only token; configure the server URL and
grant only the repository/API read permissions required by the instance.
Secrets are encrypted and are not returned to the browser or analysis prompts.

An environment consists of connection → repository → branch rows. Project and
branch selectors support search and pagination. Forks retain their own remote
identity and expose parent metadata when available. A fork's sources are never
substituted with its parent's sources. The same remote can appear in multiple
environments, or on distinct branches, while sharing its central mirror.

Editing an environment previews the changes and starts a new synchronization.
Request baselines keep their original SHAs, including commits retained after a
remote force-push. Expired authentication fails synchronization without deleting
the environment or historical requests. A referenced connection cannot disappear
silently: confirming its exact name disables it while retaining its references.

The GitHub authorization imported from older installations remains available as
a named source connection. Its source activation state also governs legacy
environment synchronization. Ticket publication retains its separate authorization.

## AI connections

Add named Codex CLI, Claude Code or Antigravity configurations, set a model, and optionally
choose a selection priority in advanced options. A configuration can share an existing provider
identity. All three assistants use official browser authorization. Antigravity
accepts a Google account, with service eligibility checked by Google; an explicitly
configured Gemini API key with billing consent is an optional alternative. Credential
namespaces and session contexts remain isolated between identities.

Model configuration belongs to each connection: **Provider / Model / Reasoning**.
Create and authenticate a connection using the provider default, then edit it and
select **Refresh models**. Shared identities can reuse an existing native catalogue.
Only the selected identity's native supported or successfully used models are
selectable. A listed model does not prove subscription entitlement. See [model access](#models-and-access-evidence).

The runtime passes the selected model to the CLI. Provider rejection makes that
configuration unavailable with an explicit diagnostic; another eligible configuration
can be tried through bounded fallback. No model is silently substituted within
the rejected configuration. A blank model and reasoning choice delegate to the provider/CLI defaults. Explicit
reasoning is passed only when supported by native metadata for that model and identity. Historical
model attribution remains unknown when it was not recorded. The former runtime
`CODEX_MODEL` override is retired; choose that exact model on each relevant
connection to retain a preferred model instead of the provider default.

Codex/Claude accept subscription OAuth only. Antigravity's explicit API mode is
separate and never an implicit fallback from Google sign-in, another provider or the host environment.
See the [Antigravity contract](antigravity.md) for supported authentication and limits.

## Status and quota observations

Select **Check connection** on an idle connection in Settings, or the sidebar's
**Refresh status and quotas** button. Authentication checks and quota reads do
not submit a business request or send an inference probe. Connection cards show
authentication, availability and quota separately; an authenticated account can
still be unavailable or have exhausted quota. **Reconnect with** renews an existing
connection through the same official authorization flow.

Codex uses the installed official app-server `account/rateLimits/read` method in
a clean credential home. It does not create a thread or turn. Only observed
windows, credit balances and reset times are displayed. Percentages are never
calculated from token counts or credit balances; model/provider limit buckets
remain separate from account-wide limits. The selected identity
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
Antigravity reads its built-in standalone `/usage` command in JSON mode. Gemini
and Claude/GPT share separate weekly pools; their percentages and reset times are
shown independently. The sidebar summarizes only the selected model's pool.
A fresh authoritative pool observation can clear that pool's earlier exhaustion,
while an unscoped account failure remains protected. Invocation token counts are
never converted into quota percentages or monetary cost.
The sidebar shows the limiting observed remaining percentage: green at 60–100%,
orange at 20–<60% and red below 20%. Unknown and authentication-required states have
no invented bar. Stale observations show **Data needs refreshing**; observation
dates and known reset times are in the keyboard-accessible **Quota details** disclosure.
Last observations and stale states remain visible offline. Visible
tabs refresh metadata every 120 seconds and at known reset deadlines; a shared
identity lock/throttle coordinates multiple browsers, and busy analyses are not probed.
Successful connection/reconnection and every completed invocation (including CLI
failures, timeouts and malformed responses) read metadata without starting a new
analysis. Post-invocation persistence does not release the existing capacity lease.
A transport/runtime outage cannot produce a fresh observation: previous data stays
visible and stale. Settings shows each reported window's observation, reset and source.

## Roles and instructions

A connection can allow Analyst, Counter-analyst and Verifier simultaneously.
**Participate in analyses** controls the connection's existing enabled state.
Disabling it retains its role assignments and credentials; role checkboxes become
read-only until it is enabled again.

**Selection priority** is the single automatic ordering setting, under collapsed
**Advanced options**. Lower values are preferred, with creation order breaking ties.
Explicit per-request selection and model-family diversity constraints still apply.
The migration converts the previous default/preference combination into numeric
priorities while preserving its ordering, including disabled connections. The
deprecated API `is_default` input remains compatible by translating a true value
into the highest numeric priority; it is no longer an independent scheduler rule.

**Role coverage** combines enabled, authenticated connections and their allowed
roles, excluding explicitly disabled model definitions. All three roles must be
covered before a new independent analysis can be queued. Incomplete settings can
still be saved. Busy connections, exhausted quota and temporary resource failures
affect immediate availability, not configured coverage: the scheduler waits using
its existing checkpoint and recovery behavior. Coverage does not certify model
diversity or override its policy. Configured models and provider defaults remain
distinct from execution metadata; task details show the reported execution model
when available rather than inventing a resolved default.

The orchestration call budget also lives in advanced options. It protects against
loops rather than limiting elapsed duration; an exhausted budget does not certify
an incomplete result.
Configure eligibility and family fallback in AI & Agents. The
[execution contract](analysis.md#execution-contract) owns scheduling, independence
and the mandatory role sequence. Labels and separate accounts do not establish diversity.

### Instruction priority and skill access

The [global skill library](#global-skill-library) owns discovery, applicability,
loading and version history. Skills grant no tool or data permissions.

Configurable instructions have two levels: common global instructions and specific
instructions on an AI connection. The effective priority is technical/security rules,
mandatory role mission, global instructions, connection instructions, then environment
documents as untrusted factual data. Environments retain their authorized sources,
documents, database and business terminology without becoming another role-policy
layer. Job snapshots retain the baseline and global configuration; a connection's
instructions are captured when that connection is assigned.

## Global skill library

### Definitions and versions

Create a global skill with an identifier, display name, objective, instructions,
expected checks and active status. New skills are global across supported
adapters; authoring does not ask for provider assignments or permission checkboxes.
Calculated capability metadata describes prerequisites for existing read-only
operations and never grants permissions. Every compatible connection discovers
active skills automatically. Full contents load only when useful.

Edits create immutable numbered revisions. Expected-version checks reject stale
submissions. The version viewer records action, timestamp and pseudonymous editing
session. Shared-password access does not identify the individual human behind it.

Disable a skill before deleting it. Historical associations do not block current global-skill deletion. Deletion
archives the entry while retaining revisions and historical analysis snapshots.
Identifiers cannot be reused for unrelated definitions.

Restoring a historical definition creates another immutable revision. It does not
replace the historical record and leaves the restored definition inactive for
review. Activating it is a separate explicit action. Restored definitions pass the
current schema, reference and capability checks; an old revision does not bypass
today's policy or make an unavailable skill active.

Export contains a versioned JSON envelope and declarative fields only. Import
previews validation before saving, rejects unknown fields such as commands or
hooks, and saves an inactive definition. Updating an existing identifier requires
the current expected version. Neither import nor restore changes the configuration
of an analysis that has already started.

### Guided creation

Choose **Generate a skill** from the global library. Describe the mission in your own words: for example, reviewing dependency
boundaries between services. The assistant asks targeted clarification questions
and proposes a declarative configuration; it does not require every field before
the conversation starts.

The discussion appears beside the editable definition and validation results.
Review the name, objective, instructions, expected checks and calculated metadata.
The assistant can recommend an existing definition from the
configured library when it fits the mission. No external extension registry is
searched or installed.

**Revise** continues the conversation. **Save as draft** retains work without
activating it. **Test in sandbox** sends a demonstration request to the shared task
queue and reports the selected connection, model, role and execution status.
Testing consumes provider capacity when the job runs. The demonstration uses an
isolated temporary session and cannot modify a repository or business database.
The test result is evidence to review, not an automatic approval.

**Activate** explicitly validates and publishes a versioned library definition.
Generation and testing cannot invoke that approval on their own. **Cancel** leaves
the current library unchanged. Active compatible skills become discoverable automatically. Inspect applicability without assigning environments or roles.

Current skill definitions use the common read-only tool surface. Provider-specific
operations do not become available merely because a skill names them. Historical
compatibility declarations remain in recorded revisions; restoring or saving a
current skill uses the global portable contract and still requires review.

### Discovery, applicability and historical context

The lightweight registry provides name, description, version, compatibility and
missing capabilities. Each assistant selects useful procedures and reads exact
read-only versioned files under `/skills` when needed. Discoverability does not
mean a procedure was loaded. Runtime file-read observations record actual loaded
versions and hashes; unavailable audit remains explicitly unknown.

Missing database/source/Web capabilities do not grant
new tools. They mark a procedure non-applicable while ordinary system analysis can
continue with the available tools. A new step observes current skill activation;
a step already running retains its frozen contents.

The job freezes global instructions and source/environment snapshots. Connection
instructions are captured when assigned; edits cannot silently rewrite previously
used instructions. Archived agent definitions and old associations remain available
for historical audit. They no longer configure current system roles.

## Models and access evidence

Choose the provider default or refresh the selected connection's native catalogue.
Codex uses `model/list` on the installed app-server. Claude Code uses the SDK
`initialize` control exchange with **no user message**; this is CLI capability
metadata, not proof of an authenticated subscription's entitlement. Antigravity
uses `agy models` and the documented read-only headless `/effort` command for the
selected model. No interactive terminal output is scraped. No hardcoded model or
effort list is offered as account availability.

The global Models settings tab has been removed. Existing API records and legacy
configured identifiers remain intact. Unverified legacy selections stay visible;
they cannot be offered as verified choices to another identity. Failed discovery
retains the last catalogue with its age/error notice. Reasoning defaults to the
provider choice, and only returned model-specific levels are selectable. Unsupported
`ultra` is excluded; execution modes are not reasoning levels. Model and effort are
frozen together for a session, so changing either starts a new session context.
See [provider verification](provider-metadata.md) for native evidence and limits.

| Status | Evidence for the selected identity |
| --- | --- |
| Unverified | Administered/legacy identifier or no usable access observation |
| Supported | Listed by adapter metadata, possibly bundled/cached; does not prove subscription access |
| Available | A real analysis successfully used that identity/model at the recorded time |
| Unavailable | An actual model rejection was observed |

**Refresh models** reads metadata without paid inference. It cannot prove
entitlement when the provider exposes no such probe. Authentication, quota health,
catalog support and actual access remain distinct. Refresh errors use fixed public
diagnostics and retain prior observations. Legacy explicit identifiers remain
unverified instead of being replaced. New explicit selections must be enabled and supported by the selected identity’s native catalogue or actual successful execution.
Disabled catalog models are excluded from new selections and scheduling.

Observed session/five-hour and weekly quota windows, reset times and freshness
remain associated with the real account. Connections sharing the identity/account
share capacity; absent observations remain unknown.

## Environments and PostgreSQL

Create repository/branch rows, optionally select PostgreSQL, then synchronize.
Editing previews changes and uses revision guards; deletion requires the exact
environment name and preserves historical baselines. Use a dedicated read-only
database account. **Test connection** checks connectivity, a read query and read-only
permissions. Owner, superuser, write-enabled and CREATE roles are rejected; this
is not a general schema or data-quality diagnostic.

### Factual context and documents

An environment can optionally supply business terminology, factual context and reference documents:
architecture notes, business terminology, conventions and constraints. Requests
continue to use their own separate attachments. No stack is assumed; actual sources
and installed dependencies determine the analysis. Environment text is untrusted
documentary data, not a third editable instruction level.

Open **Settings → Sources & environments → Environments**, then expand **Environment context** for an
existing environment. Factual context accepts up to 4,000 characters and can be disabled
without clearing them. Keep Git and database credentials in secure connection
settings. Known configured credentials are rejected in factual context and text uploads.
This is an exact credential safeguard, not a general document classification service.

Upload up to 20 documents of 25 MB each. Supported formats follow request attachments:
Markdown, TXT, PDF, DOCX, PNG/JPEG/GIF/WebP, CSV, JSON and LOG. The panel shows the
name, media type, update date, size, version and SHA-256 hash. UTF-8 text has a bounded
preview; binary or invalid UTF-8 text is identified as unreadable. Other supported
formats are inspected using the runtime's document tools; extraction may fail for
corrupt or encrypted files and should be reported by the assistant.

Toggle a document to exclude it from future analyses without removing it. Replace
it to create a new immutable content version. Remove it to hide it from the current
configuration; historical analyses retain their files. Concurrent edits use a context
revision guard and require reloading when another browser has changed the context.

Launching an analysis freezes active references and factual context. Files remain
available for relevant, on-demand exploration; their contents are not copied into the
initial prompt. Clarification keeps these references while adding the new answers.
Continuing a completed discussion picks up current reference versions while keeping
the request's Git baseline. Deleted environments use the last recorded references.

The request detail shows the frozen references for every run and selected result
version, including historical downloads. Read observations come from runtime file
access, not assistant claims. A positive observation proves a read, not understanding;
an absent observation does not prove non-use. Memory-mapped reads can be missed,
and unsupported or incomplete telemetry is shown explicitly.

### Official-reference hints

Up to twelve public HTTPS URLs or domains with notes provide non-exclusive starting
points. Saving them performs no fetch. Revision guards and frozen context apply.
[Analysis](analysis.md#official-external-references) owns research, provenance and
applicability rules; hints grant no permissions.

### Synchronization diagnostics

The environment history shows its latest twenty synchronization operations,
statuses, dates and redacted errors. Refresh reads stored history only. Git
operations and recovery are described in [operations](operations.md).

## Appearance

Open **Settings → General → Appearance** to choose
**Light**, **Dark** or **System**. The preference is saved in this browser, including
page reloads and navigation. Other tabs in the same browser update when that
preference changes. Different browsers can use different themes on the same
shared instance. System mode follows device appearance changes immediately.

The same pages, fields and actions are available in every theme. An early theme
script applies the saved preference before the first paint; the React provider
keeps it current afterward. Invalid storage values fall back to System. If browser
storage is unavailable, a notice explains that the preference lasts only for the
current tab. Interface language and existing generated files are unaffected.

Instance primary color remains a shared server setting. Appearance provides
preset swatches and a custom picker; **Save settings** applies it to the instance.
Readable foregrounds and primary text are adjusted for the active theme. State
colors remain distinct: blue running, orange waiting, muted amber clarification,
green completed and red error. Text labels accompany colors.

## Language

Select **Settings → General → Application language**, then save the settings. The
setting belongs to the shared instance. Open browsers refresh it within 15 seconds;
the browser saving it updates immediately. French is the default.

The setting controls interface labels, status notices, dates, errors, and the output
language of new analyses. Requests retain their creation language through questions,
answers, comparison, review and later discussion. Ticket and goal headings follow
that language. Changing the setting never rewrites existing artifacts or user text.
Source identifiers, schemas, repository paths and code examples keep their original
meaning and project conventions.

Translation maintenance belongs in [CONTRIBUTING](../CONTRIBUTING.md#translations).

If saved global instructions fail the existing credential-safety validation,
administration remains readable and shows a review warning instead of the obsolete
optional-verifier fallback. The rejected text is hidden and retained unchanged.
Replace it explicitly in General settings; saving an untouched blank replacement
is disabled. Analysis execution keeps its strict validation; this display recovery
does not approve or silently apply rejected instructions.
