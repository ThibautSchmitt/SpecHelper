# Security testing

Use fictional data and disposable services. Do not actively scan the shared team
instance or production databases. A clean report is bounded evidence, not security
certification. Current deployment boundaries are in [SECURITY](../SECURITY.md).

## Automated gates

The [security workflow](../.github/workflows/security.yml) defines pinned tools,
schedules, thresholds and artifact retention. Read it when changing the pipeline;
do not infer present scanner results from a dated report.

| Gate | Coverage |
| --- | --- |
| Gitleaks | Source and Git history, redacted findings; synthetic tests remain scanned |
| Semgrep | Local production-code rules, including executable input, shell execution, unsafe deserialization, TLS bypass, untrusted HTML and browser secret storage |
| pip-audit and npm audit | Frozen Python and frontend dependency graphs, including development dependencies |
| Trivy | Infrastructure definitions and actual built images, raw package/secret inventories and reviewed applicability |
| Application tests | Authentication, browser ownership, cookies/CSRF, uploads, rendering, read-only access and runtime boundaries |
| OWASP ZAP | Authenticated disposable baseline; bounded active scan on its scheduled/manual path |

Scanner jobs retain reports independently. Failed/missing scanner outcomes are not
clean results. Semgrep requires nonempty source coverage and disables hosted metrics.
Local taint rules do not establish every cross-module flow safe; browser regressions
remain necessary. Source/image scans do not upload project source to a hosted analysis
account; dependency advisory queries disclose dependency identities to registries.
Scanner containers receive no application credentials, private runtime volumes or
Docker socket.

There is no blanket dependency ignore list or broad test-source exclusion. The
[image applicability register](../security/image-applicability.json) records exact
package/image conditions and expiry, not a zero-vulnerability image. Reviews expire
within 31 days and require controls verified in the same image. They apply only where
no distribution fix is available. New identities/CVEs, fixable or unreviewed high/critical
findings, secrets and missing controls remain blocking. Raw finding counts are retained.
Review lower-severity records too.

The [infrastructure exception register](../security/trivy-exceptions.json) has one
exact DS002 exception for the trusted supervisor in `runtime/Dockerfile`, expiring
2027-01-23. It does not cover the frontend/backend or analysis child. Non-root child,
capability, credential and network rejection probes in the same image remain required.
Any new exception needs its exact location/rule, impact, owner, expiry and compensating
evidence in the register. The [dated security review](evidence/security-review.md)
preserves the original findings, including conditional OS risk and an UNKNOWN-severity
Go advisory; it is not a current scanner run.

## Disposable dynamic checks

From the repository root:

```sh
bash scripts/security/dast.sh baseline
```

For the bounded synthetic active scan, or the separate TLS probe:

```sh
bash scripts/security/dast.sh active
bash scripts/security/dast.sh https
```

These runners accept no target URL. They create a separate Compose project, random
password and temporary application data, then remove their own containers, networks
and volumes. No host ports, configured model accounts, source connections, business
databases or existing persistent volumes are mounted. They can build images and use
network access; inspect their requirements before execution.

The DAST hook authenticates only to the fixed disposable frontend origin, verifies
the session and supplies cookies/CSRF only there. It seeds pages and read API routes.
The active scan bounds spider depth/children/time and scan threads/time; inspect the
script for current values. Login/logout are excluded to preserve that synthetic
session. Deliberate rate limiting can return 429.

HTTP DAST inside the disposable Docker network does not establish production TLS.
The `https` mode uses a certificate-verified internal proxy to check Secure/HttpOnly/
SameSite cookies, CSRF, logout/replay rejection and cleartext refusal. Application
tests additionally cover Host/Origin rejection and session changes.

Reports may contain synthetic payloads and temporary sessions. Keep artifacts private
until reviewed; do not attach them unexamined to public issues. Temporary sessions
cease to exist when their disposable instance is destroyed.

## Deployment and human review

Before broad exposure, a human must review the actual reverse proxy, HTTPS, access,
firewall, kernel/container policy, backup permissions and provider retention. Automated
local checks cannot certify another deployment. The repository campaign is not an
independent professional penetration test.

Use the applicable OWASP ASVS and Web Security Testing Guide areas for authentication,
sessions, authorization/resource IDs, input/files/XSS, secrets, errors, data protection,
infrastructure and provider egress. Retain the tested revision, synthetic reproduction,
preconditions, expected/observed result, impact, correction and re-test evidence.
Do not retain a proven credential leak or a path writing analyzed business data.
