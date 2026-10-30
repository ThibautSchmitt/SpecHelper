# Security

SpecHelper is intended for a trusted team and trusted deployment administrators.
New conversations are isolated by a signed browser-owner cookie. Historical shared
records remain shared. This is not individual-user authentication, organization tenancy
or a role-based administrative boundary. Instance settings and AI connections are shared.

## Deployment and access

The default deployment publishes only the frontend on `127.0.0.1:3000`. The API,
application database, worker, agent runtime and CLI maintenance service have no host
ports. For remote access, protect the whole instance, including Administration, with
trusted infrastructure and HTTPS. Configure `BIND_ADDRESS`, `TRUSTED_ORIGINS` and
`ALLOWED_HOSTS` consistently. Do not expose a development server directly.

Set `SPECHELPER_ACCESS_PASSWORD_HASH` to a Django password hash, or mount a private
password file and set `SPECHELPER_ACCESS_PASSWORD_FILE` in frontend and backend/worker.
The file must be a regular file with mode 0400/0600 and contain 16–4096 characters.
Do not commit it. Non-loopback access without valid authentication fails closed;
passwordless local operation requires verified loopback settings.

For HTTPS, set `SPECHELPER_REQUIRE_HTTPS=1`. Enable `SPECHELPER_TRUST_PROXY=1` only
behind an isolated proxy that replaces forwarded headers and prevents direct backend
access. Sessions use HttpOnly, SameSite Strict cookies and Secure under HTTPS. Host,
Origin and CSRF checks remain required, including local operation. Password changes
invalidate access sessions. `SPECHELPER_SESSION_SECONDS` accepts 300–86400 seconds;
the default is eight hours. These access sessions differ from browser conversation
ownership and native AI sessions.

New conversation ownership uses a separate signed HttpOnly cookie. Clearing it or
changing browser does not establish the same owner; there is no human-account recovery.
Do not rely on it to protect shared administration from an untrusted team member.
Consult [Installation](docs/installation.md) before changing the reference network or
storage layout.

## Data sent to AI providers

Authorized source excerpts, uploaded files, environment reference material, bounded
query results and conversation text may be processed by the configured provider.
Authorize only resources you may disclose under your organization's and provider's
policies. Read-only access prevents mutation; it does not prevent disclosure to an
approved external model. An official sign-in does not establish a retention agreement.

Original documents and source files are untrusted data, never tool permissions or
higher-priority instructions. They must not be executed. The sandbox can access only
captured, authorized copies. File-read telemetry proves access, not comprehension,
complete provenance or freedom from prompt injection.

Public Web access uses a constrained HTTPS reader with destination validation,
DNS pinning and redirect checks. Private destinations and credential forwarding are
blocked. This is not semantic data-loss prevention: private terms included in an
external URL or query can still disclose information. Review the need and resources.

Structured progress excludes private reasoning, raw commands and unrestricted tool
output. Configured-secret and common-pattern redaction reduces accidental exposure
but cannot identify every confidential fact. Short configured credentials use complete
token matching; long credentials and credential-bearing URLs are masked more broadly.
Redaction does not rewrite already stored history. Review exports and transferred
context before sharing them.

## Credentials and encryption

Keep `.env`, access files, database dumps, native sessions and private reports out of Git.
Application credentials are encrypted with the key named by `ENCRYPTION_KEY_FILE`.
The reference deployment persists that key under application data. Runtime AI profiles
use a separate, domain-separated key derived from its control secret. Preserve these
keys and secrets alongside consistent backups; replacing them can make retained
credentials or sessions unusable. Encryption does not protect against a trusted
administrator controlling the running service and its keys.

Git and business database credentials stay outside model prompts and child filesystems.
The trusted brokers authenticate authorized operations. Provider profiles/tokens remain
in the runtime vault; analysis children receive scoped synthetic capabilities rather
than reusable provider secrets. Account metadata can remain public instance configuration.

Antigravity supports official Google account sign-in and a separate optional Gemini API
mode with explicit billing consent. Credentials are injected only at the fixed upstream
relay for the selected mode. Host API keys, browser accounts and keyrings are not implicit
fallbacks. Session recovery does not silently change provider, account or model.

## Runtime boundary

The trusted Linux namespace supervisor requires root plus `SYS_ADMIN`/`NET_ADMIN`
and relaxed container-level seccomp/AppArmor settings in the reference deployment.
This is an explicit residual privilege, not an ordinary unprivileged container.
It has no Docker socket, application database or Git-source credentials. The host,
kernel and deployment administrators are trusted.

Analysis children run as a distinct non-root UID/GID with capabilities dropped,
no-new-privileges and child seccomp restrictions. Authorized sources, attachments and
documents are read-only. Each execution has scoped writable session/temp space and
brokered network access. Namespace/control failures fail closed. Retain these controls
when changing Compose, building images or increasing concurrency; shared resource
limits bound aggregate work, not provider quota.

## Business data, files and publication

Business PostgreSQL requires a dedicated reader: no superuser, ownership, write or
CREATE privileges. Runtime queries use read-only transactions, SQL validation, a
five-second statement bound and limited results. No database snapshot is implied by
capturing a connection. Do not grant writes to bypass a failed connection test.

Uploads are bounded by type, signature and size, including DOCX container inspection.
Supported originals are limited to 25 MB each; environment context accepts at most
20 documents. Executables and arbitrary archives are not accepted. A valid document
can still contain sensitive data or malicious instructions.

Ticket publication uses encrypted, separate connector credentials and explicit human
confirmation of an allowed destination. GitHub publication must not reuse Git-source
credentials. Agents cannot publish through their analysis tools. Verify the preview,
required fields and optional files; a successful connection test does not prove write
permission. Uncertain external writes must be reconciled before another creation
attempt. See [Usage](docs/usage.md#prepare-and-publish-a-ticket).

## Retention and backups

Captured Git baselines, original reference-document versions, messages, decisions,
results, native sessions and publication audit records may contain private material.
Disabling/removing a reference or deleting an analysis from active views does not
securely erase retained versions, linked history or published tickets. There is no
automatic business-content purge. Access-event retention is separately configurable
with `SPECHELPER_AUDIT_RETENTION_DAYS` (1–365, default 30).

Back up application PostgreSQL, persistent resource/session volumes and keys together.
Protect and test restore procedures outside production. Source workspaces and frozen
context deserve the same access controls as uploads. External providers and ticket
systems retain their own copies according to their policies.

## Validation and reporting

[Security testing](docs/security-testing.md) describes scanner gates and disposable
probes. The [dated security review](docs/evidence/security-review.md) is bounded evidence,
not certification of the current host, reverse proxy, provider service or every answer.
Independent human deployment review remains necessary before broad exposure.

Do not disclose secrets or real data in a public issue. Use GitHub's **Report a
vulnerability** when private reporting is enabled. Otherwise ask the maintainer for
a private channel without publishing exploit details. Include the source revision,
minimal synthetic reproduction, impact and prerequisites. Never send AI, Git or
database credentials, private attachments or production dumps.
