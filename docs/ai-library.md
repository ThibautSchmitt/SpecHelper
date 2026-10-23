# AI connections, models and the shared library

Open **Settings → AI & Agents**. Five sections separate connections, models,
public roles/orchestration, agent definitions and skill definitions.

A connection selects an authenticated provider identity, model, eligible public
roles and execution preferences. An agent defines a mission and required skills.
A skill defines a reusable declarative procedure. Two connections do not establish
independent subscription quotas; an agent never introduces a new execution privilege.

## Portable definitions and versions

Create an agent or skill with an identifier, display name, objective, instructions,
active status, allowed providers and required capabilities. An empty provider
selection allows both supported adapters. Capabilities describe prerequisites for
existing read-only operations; they never grant permissions. Agents reference
active skills from the shared library without copying their contents.

Edits create immutable numbered revisions. Expected-version checks reject stale
submissions. The version viewer records action, timestamp and pseudonymous editing
session. Shared-password access does not identify the individual human behind it.

Disable a definition before deleting it. Remove references from agents and explicit
environment selections first. Required workflow agents cannot be deleted. Deletion
archives the entry while retaining revisions and historical analysis snapshots.
Identifiers cannot be reused for unrelated definitions.

## Environment selection and preview

Under **Settings → Environments**, open **Agents and skills for this environment**.
Inherit active definitions or select explicit references. Requirement, code and
writer agents remain necessary. Custom agents supplement the workflow with mission
instructions; they do not add executable hooks.

Select an AI connection and preview the unsaved selection. The preview includes
selected versions, provider adaptation, model, connection instructions and
public-role instructions. Incompatible providers, missing capabilities, unavailable
required skills and conflicting connection overrides produce explicit diagnostics.
The interface requires a compatible preview before saving; the backend validates
references and revision independently. Incompatible execution fails rather than
selecting a more permissive tool.

An enqueued analysis freezes full library definitions alongside its environment
context. Actual connection instructions/skill overrides are retained per working
session. Later edits, deactivation and deletion do not rewrite those instructions
or published artifacts. Legacy analyses cannot retroactively recover configuration
that was never stored.
The historical result's frozen-context panel shows retained agent/skill versions
and their original instructions without consulting the current library.

## Models and access evidence

Choose a catalog model or the provider default. Refresh metadata for a specific
connection where the adapter exposes it. Codex uses the installed app-server's
bounded model-list protocol without starting inference. Claude currently has no
validated non-inference discovery here: add documented identifiers explicitly;
no model list is invented.

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
role uses a separate working session. Verification is optional. With two eligible
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

Copilot is **experimental and unavailable for production analysis**. Read the
[adapter evaluation](copilot-evaluation.md) for the authentication, quota, session
and network checks required before activation.
