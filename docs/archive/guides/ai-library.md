> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# AI connections, models and the shared library

Open **Settings → AI & Agents** for connections, models, role eligibility and the
global skill library. Mandatory Analyst, Counter-analyst and Verifier missions come
from the orchestrator. Configure common instructions in General and specific
instructions on a connection. Neither layer grants extra execution privileges.

## Portable definitions and versions

Create a global skill with an identifier, display name, objective, instructions,
expected checks and active status. New skills are global across both supported
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

## Guided creation

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

## Discovery, applicability and historical context

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

Choose a catalog model or the provider default. Refresh metadata for a specific
connection where the adapter exposes it. Codex uses the installed app-server's
bounded model-list protocol without starting inference. Claude currently has no
validated non-inference discovery here: add documented identifiers explicitly;
no model list is invented.
The detected catalogue is shown first; manual additions remain behind a secondary action.

| Status | Evidence for the selected identity |
| --- | --- |
| Unverified | Administered/legacy identifier or no usable access observation |
| Supported | Listed by adapter metadata, possibly bundled/cached; does not prove subscription access |
| Available | A real analysis successfully used that identity/model at the recorded time |
| Unavailable | An actual model rejection was observed |

**Check model** refreshes metadata without paid inference. It cannot prove
entitlement when the provider exposes no such probe. Authentication, quota health,
catalog support and actual access remain distinct. Refresh errors use fixed public
diagnostics and retain prior observations. Legacy explicit identifiers remain
unverified instead of being replaced. New selections must be enabled catalog entries.
Disabled catalog models are excluded from new selections and scheduling.

Observed session/five-hour and weekly quota windows, reset times and freshness
remain associated with the real account. Connections sharing the identity/account
share capacity; absent observations remain unknown.

## Roles, diversity and history

A connection may simultaneously allow Analyst, Counter-analyst and Verifier. Each
role uses a separate working session. Independent verification is mandatory. With two eligible
families, orchestration prefers A → B → A; with three it prefers A → B → C.
Explicit model-family metadata takes precedence over provider defaults. Display
names, separate sessions and accounts do not establish different families. Declare
the documented underlying family, not a label for increasing apparent diversity.

Without an alternative family, administrators choose explicit independent-session
fallback or waiting. A forbidden role is never substituted. Queue cards show the
connection, provider artwork, actual model and public role; completed steps retain
execution snapshots and provider-change warnings. The business comparison checkbox
remains absent from request/question forms.

## Security and experimental adapters

Definitions are text inputs to the existing constrained runtime. No API accepts
executable hooks, arbitrary tools or additional sandbox permissions. Source/database
writes, reusable credentials, other sessions and arbitrary network destinations
remain forbidden. Known configured credentials are rejected in definitions and
redacted at prompt/output boundaries.

Generation receives only the submitted conversation and the configured library
information needed to propose a definition. It does not receive connection
credentials, arbitrary environment documents or other analyses. Generated content
is untrusted input and passes the same deterministic checks as direct editing,
import and restoration. Those checks reject unsupported fields, missing skill
references and explicit requests for additional privileges. Runtime isolation and
central policy remain the final enforcement boundary; text screening does not
establish a general proof that a prompt is harmless.

Remote access to generation, editing, sandbox tests and activation requires the
instance's authenticated shared-team session and CSRF protection. The local-only
access mode remains available on a loopback-bound instance. This application does
not introduce individual administrator accounts or separate team permission roles.

Copilot is **experimental and unavailable for production analysis**. Read the
[adapter evaluation](copilot-evaluation.md) for the authentication, quota, session
and network checks required before activation.
