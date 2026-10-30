# Configuration

Open **Administration** at the bottom left; it opens **AI & Agents → Connections**.
The main sections are **AI & Agents**,
**Environments**, **Ticket publication** and **Appearance**. They are not separate sidebar
menus. This guide uses the English interface labels; the application also supports French.

Use the add button at the right of a section heading to create a connection,
environment or skill. **Edit** opens the form inside the selected item's card;
select **Edit** again or **Cancel** to discard unsaved changes and collapse it.
Editors use **Cancel** and **Save**. Saving an environment applies its changes
directly; synchronization is scheduled only when its resources change.
Orchestration has its own configuration card and no add button.

## Git sources and environments

Under **Environments → Manage Git connections**, connect GitHub or GitLab using the authorization
or token method offered for that provider. GitLab can use a self-hosted instance URL.
Use only accounts authorized for the selected repositories. Source checkout and ticket
publication are separate operations with separate credentials.

GitHub source connections currently support `https://github.com` only; GitHub
Enterprise servers are not supported. Select GitLab to enter a custom GitLab URL.
An unused GitLab connection's URL can be edited with a new read access token;
this clears cached project discovery and the previous account/test status.
For connections referenced by an environment or analysis history, add a new
connection instead of changing the server of existing repository references.

Create an environment under **Configured environments**:

1. Give it a useful name such as Development or Staging.
2. Select repositories from the saved Git connections and choose their branches/tags.
3. Optionally select a saved PostgreSQL connection.
4. Synchronize and check the recorded outcome and last synchronization time.

Connections are reusable across environments. Repository rows retain their selected
connection and reference. Synchronization records Git SHAs; subsequent analysis
uses a frozen baseline rather than a branch that can move during investigation.
Git updates are performed by the source service, never by an analysis agent.

An environment can also hold optional factual context, terminology, public-reference
hints and reference documents. Expand **Environment context** to manage them.
Context text is limited to 4,000 characters. Up to 20 documents of 25 MB each can be
provided in supported image, PDF, DOCX, text, Markdown, CSV, JSON or LOG formats.
Unsupported archives, executable content and unsafe DOCX containers are rejected.

A document replacement creates an immutable content version. Disable or remove it
from future work without rewriting historical analysis copies. Removing an environment
also preserves referenced analysis history. Git/context resources and database selection
are captured for the discussion or deep cycle; changing settings does not rewrite
an earlier verified result. A later explicit deep analysis captures its own context.

Public HTTPS reference hints are starting points, not instructions or permission
grants. Saving a URL does not visit it. The constrained Web reader is used only
when an authorized analysis needs external references; private destinations are blocked.

## Optional business PostgreSQL

Use **Environments → Manage PostgreSQL connections** to save and test a dedicated reader,
then select that connection in an environment. This database is separate from
SpecHelper's own application PostgreSQL.

The reader must not be an owner or superuser and must not have write or CREATE
privileges. Testing checks connectivity, a read query and the required restrictions;
it does not validate the whole schema or business data. Runtime queries additionally
use read-only transactions, SQL validation, timeouts and bounded results. Database
credentials stay outside prompts and the agent filesystem.

A saved database reference is not a frozen data snapshot. Conclusions about actual
records need a recorded observation period, scope and limits. Without access,
SpecHelper can describe code behavior but cannot claim to have checked live records.

## AI connections

Under **AI & Agents → Connections**, add a named connection:

| Provider | Connection and session behavior |
| --- | --- |
| ChatGPT / Codex | Guided official account authorization; discussion resumes the recorded native thread when available. |
| Claude / Claude Code | Guided official authorization; discussion uses the recorded native session when available. |
| Antigravity | Official Google-account flow. An optional Gemini API key requires separate, explicit billing consent; it is never an implicit fallback. Discussion resumes the recorded native conversation when available. |

Complete browser authorization in the provider's official page. If a code is
requested, submit it only through the connection dialog. Account/region/subscription
eligibility is determined by the provider. SpecHelper does not import host browser
cookies, keyrings or ambient API keys as a fallback.

Select a model from **Refresh models**, then the reasoning level when that model
exposes a separate supported choice. Codex/Claude can retain a provider default;
Antigravity requires an explicit model. Some Antigravity model identifiers already
encode reasoning, so no separate reasoning field is shown for them. The form chooses
`medium` when it is reported by the selected model, otherwise a supported native level.
It does not invent capabilities or offer unsupported levels.

A model catalogue describes the installed CLI's capabilities, not guaranteed
subscription entitlement. Updating the CLI may be needed before new models appear.
Failed discovery retains previous observations. A real provider rejection remains
a model/access error; it must not silently change the chosen model.

Each connection card shows its status, selected model, allowed role tags and installed
CLI version. **Edit** opens inside that card; selecting it again cancels editing.
**Change account** restarts authorization and may renew the same account or select
another. **Disable** preserves configuration and credentials but removes eligibility.
Do not change an account's configuration while its invocations are still active.

The application detects installed/latest CLI versions and offers **Update** when
appropriate. Updates are explicit, drain active invocations and retain rollback/
uncertain states. Model refresh and version checks do not themselves run an analysis.

Antigravity's official rolling release manifest is checked again when an update
starts, so an outdated catalogue entry cannot pin the operation to an obsolete
download. The runtime checks the selected installed release and its required
capabilities, including after an update; it does not require the original image's
version forever. Failed installation and service unavailability are reported
separately, and unsuccessful activation checks restore the previous executable.

### Availability and quotas

Expand **Quotas** in the connection card for observed windows and timestamps.
The sidebar contains a compact, model-relevant summary with a global refresh action.
Multiple limiting windows use the most restrictive applicable observation. Other
model families are not treated as exhausted merely because one pool is depleted.

Antigravity reports Gemini and shared Claude/GPT pools separately. Its red exhausted
badge represents observed total weekly exhaustion across those pools. A five-hour
limit, one depleted family or missing data does not establish total exhaustion.
Percentages, reset times and credits are displayed only when reported. Old readings
remain distinguishable from fresh observations; no reset date or quota is estimated.

**Refresh status and quotas** reads authentication/quota metadata without inference.
Visible clients refresh metadata periodically and at known reset deadlines, with a
shared throttle. Each completed invocation also refreshes available metadata, including
failure/timeout paths. A transport outage preserves previous observations rather than
claiming a fresh measurement. Metadata checks may defer while the account is in use.
Authentication alone does not establish quota recovery or concurrent provider capacity.

Several conversations may share an account with isolated sessions. Account aliases
share the same quota and execution-slot budget. Discussions remain pinned to their
selected account/model; they do not move silently when it is busy. Configure the
[account and instance ceilings](installation.md#concurrent-work) at deployment.

## Analysis roles and skills

**AI & Agents → Orchestration** shows Analyst, Counter-analyst and Verifier coverage
and the connections eligible for each role. The French labels are Analyste,
Contre-analyste and Validateur. A connection can cover several roles; no separate
participation checkbox is needed. Busy accounts or exhausted quotas affect immediate
availability, not whether a configured role exists.

All three roles must be covered to launch deep analysis. The Counter-analyst first
examines the need independently. Each role uses an isolated session; the discussion
session is not reused as a role session. If configured fallback permits the same model
family, distinct sessions do not become distinct families. Full/partial/limited family
diversity is descriptive, never a confidence percentage.

SpecHelper supplies its native analysis method and fixed progression safeguards.
There is no standard global prompt editor or total AI-call-count setting. A step must
produce accepted progress; empty/repeated transitions, unsafe outputs and technical
failures are not bypassed to obtain a completed label.

**AI & Agents → Skills** separates maintained built-ins from custom procedures:

- Built-ins are read-only and automatically discoverable when their required tools are allowed.
- Custom skills can be created, generated with assistance, imported, edited, disabled,
  restored and exported. Changes create immutable revisions; imported/restored drafts
  remain inactive until explicitly reviewed and activated.
- Assistants see a lightweight registry and load useful contents on demand. A discovered
  skill is not necessarily read. Recorded file access proves access, not comprehension.
- Skills and per-connection instructions cannot grant tools, network access or write permissions.

For advanced deployments, `SPECHELPER_ANALYSIS_POLICY_FILE` can name a read-only
UTF-8 policy file mounted into both backend and worker. It is bounded and validated;
it adds guidance below the native method, not permissions. Preserved custom guidance
from earlier installations is retained for review, not silently activated.

## Ticket connectors

Under **Ticket publication**, manage the instance-wide catalogue of publication
connections. Give each connection any useful name. Several connections may use the
same provider; renaming keeps the stable connection ID, credentials and associations.
Use **Test connection** to observe its real status. A name-only edit retains that
observation; credential changes require verification again. Disable a connection to
prevent new publication without deleting its credentials or history.

Under **Environments**, **Publication destinations** selects zero, one or several
catalogue connections. The selector is available during creation and editing; the
current associations are also shown on each environment. One connection may be used
by several environments and several accounts of one provider may share an environment.
Changing only these associations does not resynchronize Git or rerun an analysis.

A connection authenticates an external account. A destination is a repository,
project, entity or other accessible target. Choose the effective connection and
actual destination at publication time. Optional project restrictions/defaults remain
connection settings; an empty restriction list allows destinations accessible to the
account. Actual access is rechecked by the provider adapter before a new write.
Untested, failed, unavailable and disabled connections are shown but unavailable
for selection. Saving or testing a connection does not publish a ticket.

| Destination | Implemented adapter |
| --- | --- |
| GitHub Issues | github.com, dedicated issue-publication token and allowed repositories |
| GitLab Issues | GitLab cloud or self-hosted REST v4, with suitable project issue permissions |
| Jira | Jira Cloud REST v3, instance URL, account email and API token |
| GLPI | Legacy REST v1 (`apirest.php`), enabled API, user token or username/password; app token when required |

GitHub Enterprise, Jira Data Center and the newer GLPI API are not implemented by
these adapters. Publication OAuth is not implemented; Git source authorization does
not establish publication rights. GitHub publication must not reuse repository-read
credentials. A successful test is not proof of every destination's write permissions.

Connection endpoints with publication history cannot be retargeted. Create another
connection for a different instance, preserving recovery links to existing tickets.
Deleting an associated connection requires unlinking it first. Publication history
prevents deletion; disable the connection instead. Existing single-environment
associations migrate to the shared catalogue without copying accounts or decrypting
secrets. Unassociated connections remain available for explicit configuration.

These accounts are shared by the trusted instance. The selected external account
performs publication; it need not identify the person operating SpecHelper. No new
individual SpecHelper account or per-connection user permission is introduced.
See [Usage](usage.md#prepare-and-publish-a-ticket) for previews, templates and attachments.

## Appearance and language

Under **Appearance**, configure the instance name, optional subtitle, primary color
and application language. Theme selection (Light, Dark or System) is saved per browser;
the color, name and language are instance settings. The same functions exist in every
theme. French is the initial application language.

An analysis keeps its creation language in subsequent questions, results and deliverables.
Changing instance language does not translate user input or rewrite existing artifacts.
