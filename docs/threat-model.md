# Threat model and trust boundaries

SpecHelper is one shared instance for a trusted team. Authentication grants access
to the team's requests, attachments, settings and connections with equal permissions.
It does not create private user workspaces or tenant boundaries. Do not host mutually
untrusted organizations in the same instance.

## Assets and adversaries

Sensitive assets include private source code, business documents, database results,
prompts, generated reports, Git and AI credentials, application encryption keys,
session cookies and immutable analysis history. Relevant adversaries are anonymous
web clients, hostile repository/document/ticket/database content, an analysis process
following injected instructions, compromised dependencies, and deployment mistakes.
Host administrators and the trusted runtime supervisor can access secrets by design;
a fully compromised host is outside the analysis sandbox's protection.

## Boundaries and enforced permissions

| Boundary | Trusted component | Enforcement and residual exposure |
| --- | --- | --- |
| Browser to frontend/API | Application access middleware | Remote exposure requires shared-password authentication; cookies, expiry, rotation, revocation, CSRF, exact Host/Origin checks and shared database rate/concurrency accounting apply before resource lookup. All authenticated sessions share team permissions. |
| API to application database | Backend/worker | Connection secrets are encrypted. The encryption key is stored separately from PostgreSQL. The application necessarily decrypts technical credentials to operate; restrict host and volume access. |
| Worker to runtime | Private control capability | Internal network, bearer capability and no published runtime port. The analysis namespace cannot read the control volume or application database. |
| Git synchronization to source volumes | Git service | Clone/fetch/checkout creates mirrors and immutable analysis workspaces. The analysis namespace receives read-only mounts, with no repository credentials or Git network access. |
| Runtime supervisor to analysis child | Linux namespace supervisor | UID/GID 10001, no capabilities, no new privileges, isolated PID/mount/network namespaces, read-only runtime/source/document mounts and a single writable session. Failure to establish isolation aborts execution. |
| Child to AI provider | Per-run broker | Synthetic short-lived capability, exact provider endpoint allowlist, real OAuth injected only by the trusted broker, no redirects/environment proxies, bounded request/response/time. Arbitrary destinations are denied. |
| Child to business database | Controlled query capability | Dedicated role must be non-owner and have no write/CREATE privileges. Read-only transaction, SQL validation, timeout and row limit provide additional controls. No database password enters the child. |
| Attachment to parser | Constrained analysis namespace | Actual type checks, bounded upload/ZIP expansion, random internal names and read-only mounts. PDF/DOCX/image data cannot grant executable permissions or alter the namespace. |
| Human to ticket destination | Publication service | Explicit confirmation and allowed target. Publication credentials must be distinct from repository-read credentials. AI analysis cannot invoke publication through its broker. |

## Credential lifecycle

Database-held Git, ticket and PostgreSQL secrets use authenticated encryption.
`ENCRYPTION_KEY_FILE` defaults to `/data/encryption.key`, outside the PostgreSQL
volume. Its ACL must exclude group/other access. Back up this file separately from
database exports and restrict access to both backups.

CLI `auth.json`, `.credentials.json` and `.claude.json` files are encrypted using a
domain-separated HKDF key derived from the runtime control secret. Startup seals
legacy files in both the credential store and retained session directories
atomically, verifies encryption before replacing them, and preserves their paths
and account identities. Disposable malformed, oversized or linked session credential
copies are removed without following links; the trusted credential store fails
closed instead. Losing or replacing the control secret prevents
decryption: restore the matching secret from a protected backup or reconnect the AI
accounts. Do not rotate the control secret independently of the credential backup.

Only the trusted supervisor decrypts provider OAuth. Status/quota/login operations
may materialize private plaintext files in `/tmp`, which is a container tmpfs with
private temporary directories and file mode 0600. They are removed at operation end.
Analysis children receive synthetic credentials for their per-run broker. Real
credentials exist in trusted process memory during authentication and upstream calls;
there is no claim of zero secrets in memory. OAuth renewal preserves account/scope
metadata and cannot replace a newer login. Revoking a provider account invalidates
its upstream authorization; reconnect it through Settings.

The API response boundary redacts configured credentials from textual responses and
exports without rewriting immutable historical records. Exact matching and common
token-pattern detection do not identify every confidential business fact. Review
artifacts before sharing them outside the team.

## Provider transfer and retention

Code excerpts, submitted business needs, selected context documents, attachment
contents and permitted database results may be sent to the selected AI provider.
The destination restriction prevents arbitrary network exfiltration; it does not
prevent business data transfer to that selected provider. Configure only accounts
whose contractual data handling and retention meet the team's requirements.
SpecHelper cannot override a provider's retention or account policies.

Prefer a narrowly scoped environment, necessary documents only, dedicated read-only
database roles and minimal queried columns/rows. Do not upload technical credentials.
Agents treat repository comments, README files, PDF text, tickets and database cells
as untrusted evidence. Prompt injection cannot grant new filesystem/network/database
permissions; tests must attempt the forbidden operation to verify this boundary.

Requests, generated versions, source baselines, context versions and attachments are
retained for reproducibility. Removing a context document from an environment does
not remove historical versions. Backups and exported reports need the same access
restrictions as the live instance. No automatic business-history deletion policy is
implied. Security-event retention is independently configurable through
`SPECHELPER_AUDIT_RETENTION_DAYS` (1–365, default 30). Audit records use fixed action
categories and pseudonymous actors, excluding raw content, queries and credentials.

## Container privileges and deployment assumptions

The trusted runtime supervisor requires root and namespace setup capabilities.
Analysis children have a distinct non-root identity and zero effective/bounding
capabilities. After dropping privileges, a fail-closed libseccomp filter blocks
namespace/mount changes, tracing other processes, kernel modules, BPF, keyring and
other privileged kernel interfaces. Descendants inherit the filter across exec.
Compose currently relaxes the supervisor's seccomp/AppArmor profiles
for Bubblewrap compatibility. This is a deliberate residual host boundary: use a
dedicated host/VM and do not expose the runtime API or share its control network
with untrusted workloads. Custom host security profiles require testing on that host.

Container CPU/memory/PID limits, per-run time/descriptor/file limits, a bounded tmpfs
and session-size monitoring limit resource exhaustion. Monitoring is not an atomic
per-directory filesystem quota; keep the session volume on a monitored, capacity
limited filesystem. Host resource exhaustion remains an operational concern.

See [security testing](security-testing.md) for the scanner gates, findings, exact
exceptions and targeted review scope. Passing tests do not certify another host's
proxy, TLS, kernel policy or provider account configuration.
