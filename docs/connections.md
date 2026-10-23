# Git sources and AI connections

Connections belong to the shared team instance. Settings separates source access,
terminal assistant authentication and ticket publication permissions.

## Git sources

Use **Settings → Environments → Sources Git** to add named GitHub or GitLab connections. GitHub
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

## Terminal assistant configurations

Add named Codex CLI or Claude Code configurations, set a model, and choose a
default or numeric preference. A configuration can share an existing provider
identity or authorize another account through the official browser flow. Credential
namespaces and session contexts remain isolated between identities.

Use **Settings → AI & Agents → Models** to refresh adapter metadata or register a
documented model before selecting it. Model access is identity-scoped; a listed
model does not prove subscription entitlement. See the [model and library guide](ai-library.md).

The runtime passes the selected model to the CLI. Provider rejection makes that
configuration unavailable with an explicit diagnostic; another eligible configuration
can be tried through bounded fallback. No model is silently substituted within
the rejected configuration. A blank model delegates to the configured runtime/CLI
default; historical model attribution remains unknown when it was not recorded.

Only subscription OAuth credentials are accepted. An API key from the environment
or a user's CLI configuration is not an implicit paid fallback.

## Availability and quotas

Availability follows provider/runtime observations. Configurations sharing an
identity share its quota and capacity. Separate authorizations are grouped only
when the provider exposes a reliable matching account identifier; display names
are not evidence that accounts are identical.

Session and weekly quota windows appear only when reliable telemetry is available.
Missing windows show **Unknown**. SpecHelper does not estimate percentages, reset
times or remaining tokens. A known exhausted account is excluded until recovery
is established or an officially reported reset has passed. Authentication health
alone does not establish quota recovery.

If no eligible assistant is available, requests remain in the persistent queue.
Queue cards show no active assignment before execution, then the selected connection
and model. Per-step execution snapshots retain the connection, provider, model and
failure/fallback history even when a configuration is later renamed or changed.
