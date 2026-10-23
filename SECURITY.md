# Security

SpecHelper is designed for a trusted team. An instance shares requests and connections
and provides no individual accounts or private spaces. Remote instances require
application access authentication; protect the deployment with HTTPS and trusted
team infrastructure as well.

## Deployment

The default deployment publishes only the frontend on `127.0.0.1:3000`. Neither
the API nor the agent runtime exposes a host port. For remote access, protect the
entire instance, including Settings, with your team's VPN, reverse proxy or SSO,
serve it over HTTPS, and configure `BIND_ADDRESS`, `TRUSTED_ORIGINS` and
`ALLOWED_HOSTS` for the deployment.

Set `SPECHELPER_ACCESS_PASSWORD_HASH` to a Django password hash, or mount a protected
password file and set `SPECHELPER_ACCESS_PASSWORD_FILE` to its container path. A
password file must be a private regular file with mode 0400/0600 and contain 16–4096
characters. Do not commit it. Both frontend and backend/worker must use the same
deployment settings. A non-loopback instance without valid access configuration
fails closed. Local access without a password requires verified loopback settings.

For HTTPS, set `SPECHELPER_REQUIRE_HTTPS=1`. Enable `SPECHELPER_TRUST_PROXY=1` only
behind an isolated, trusted proxy that replaces forwarded headers and prevents
direct backend access. Session cookies are HttpOnly and SameSite Strict, Secure
under HTTPS. Password changes invalidate existing sessions. The default session
duration is eight hours; `SPECHELPER_SESSION_SECONDS` accepts 300–86400 seconds.
CSRF protection remains required for changes even in localhost mode.

The [threat model](docs/threat-model.md) documents data transfers, encryption keys,
CLI credential handling, retention, trusted components and residual host privileges.
The [security campaign](docs/security-testing.md) documents scanner and pentest scope.

Source workspaces and attachments are mounted read-only in the agent sandbox.
Analyzed PostgreSQL databases require dedicated read-only roles. GitHub and
database credentials are not added to AI prompts. Attachments remain untrusted
data and must never be executed as instructions.

Ticket connector credentials are encrypted on the server and are excluded from
analysis prompts and API responses. Publication is a separate backend operation
that requires explicit human confirmation and an allowed destination. Review
the target and content before creating a ticket. After an uncertain response,
verify the recorded operation rather than creating another ticket manually.

The Linux sandbox requires specific namespace capabilities and network boundaries.
Preserve those boundaries when adapting deployment; see
[implementation notes](docs/implementation.md#services-and-runtime).
See [operations](docs/implementation.md#operations) for coordinated backups and
persistent volumes.

## Reporting a vulnerability

Do not disclose vulnerabilities containing secrets or real data in a public issue.
Use GitHub's **Report a vulnerability** if private reporting is enabled. Otherwise,
ask the maintainer for a private channel without disclosing exploit details.

A useful report includes the version, minimal reproduction, impact and prerequisites, using fictional data. Never send AI, GitHub or database credentials or private team attachments.

Environment reference documents are untrusted input. Original versions are retained
for historical analyses; removal from an environment does not erase those versions.
The runtime sees only verified frozen copies through a dedicated read-only volume
and per-file sandbox bindings. Include original context resources in backups and
apply the same access controls as source workspaces and attachments. File-read
telemetry reports access, not semantic understanding or complete data provenance.


Question explanations and documentation inherit the same shared-instance access
controls as requests. Transferred context is an isolated, read-only attachment,
not privileged agent instructions. It contains curated findings and provenance,
not original documents or private agent reports. Review it before creating a
request; exact configured-secret redaction cannot identify every sensitive fact.
Later source changes require verification against the new request's current
baseline. Referenced question versions and generated documents are retained.
