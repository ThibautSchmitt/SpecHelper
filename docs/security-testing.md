# Security validation and release review

Security testing uses fictional data and disposable services. The shared development
instance and production services are never active-scan targets. A clean report is
bounded evidence, not a guarantee of security.

## Automated campaign

`.github/workflows/security.yml` runs on pushes and pull requests. Each scanner
produces a report even if another scanner fails; the final source gate rejects any
failed or missing scanner outcome. Reports are retained for 14 days (DAST 7 days).

| Gate | Coverage |
| --- | --- |
| Gitleaks 8.30.1 | Full Git history, redacted JSON, default detection rules; tests remain scanned |
| Semgrep 1.143.0 | Local production-code rules for executable input, shell execution, unsafe deserialization, TLS bypass, HTML injection from API/browser input and browser secret storage |
| pip-audit 2.9.0 | Exact Python runtime and development dependencies exported from the frozen lock |
| npm audit | Exact package-lock dependency graph, including development dependencies |
| Trivy 0.67.2 | Infrastructure definitions and exact built images; raw package/secret reports are retained; unreviewed or fixable high/critical findings block |
| Application tests | Auth, cookie policy, CSRF, shared-instance access boundaries, uploads, rendering and runtime isolation |
| OWASP ZAP | Authenticated baseline on every update; bounded active scan weekly or explicit manual dispatch |

Semgrep uses local rules and metrics are disabled. Its HTML rule follows API/browser
input to raw HTML sinks; a fixed nonce-bearing theme bootstrap is trusted code,
not an untrusted HTML source. Local taint analysis does not prove all cross-module
flows safe; browser XSS regression tests remain necessary. Source and image scanners do not
upload project source to a hosted analysis account. Dependency advisory queries
send dependency identities to their registries. Scanner containers never receive
application credentials, the Docker socket or private runtime volumes.

No scanner-level dependency ignore list or broad test-source exclusion is installed.
`security/image-applicability.json` records individual OS finding reviews for exact
package URLs and image components. These expire within 31 days, require same-image
control probes and apply only where the scanner reports no available distribution
fix. High/critical application-package findings, new package versions, new CVEs, secrets and missing
controls remain blocking. The original Trivy report is retained with its real finding
count; a separate review summary never relabels it as a zero-vulnerability image.
The GitHub CLI review identifies an upstream-fixed vendor version that Debian's
source-package tracker still flags, and requires an actual binary-version probe.

Unused infocmp/Perl Archive::Tar code and SUID/SGID permission bits are removed from
final images; global pip/npm/uv build tooling is removed where unused. Conditions
also verify absent homed/TPM/tiffcrop/X11 components. Runtime findings additionally
require the exact image's UID, capabilities, seccomp, source/session, credential,
network and four-carrier injection probes. Read the complete
[applicability register](../security/image-applicability.json) and
[targeted review](archive/reports/security-review-v1.9.md) before adapting the reference deployment.
`security/trivy-exceptions.json` contains one exact infrastructure exception for
DS002 in `runtime/Dockerfile`: the trusted namespace supervisor requires root,
whereas analysis children must run as a distinct non-root identity. Runtime
credential, capability and network-rejection probes are mandatory compensating
evidence. This expires on 2027-01-23 and does not cover any other image or rule.
Any future exception must name the scanner/rule, exact affected location, impact,
compensating control, owner and expiry in the findings table below. Scanner errors
and missing reports are failures, not clean results. Review all severities in the
JSON artifacts, including findings below the blocking severity threshold.

## Disposable DAST

Run `scripts/security/dast.sh baseline` from the repository. Use
`scripts/security/dast.sh active` only for the bounded, synthetic local target.
Neither command accepts a target URL. Both build a separate Compose project,
create a random password file, use temporary application data and tear down their
containers/network/volumes on exit. No host ports, Git connections, model accounts,
customer databases or existing persistent volumes are mounted.

The hook authenticates to `http://frontend:3000`, verifies the session, adds cookies
and CSRF only for that fixed origin, and seeds the main pages plus read API routes.
The active scan limits the spider to 1 minute, depth 3 and 20 children; active work
has a 4-minute scan limit, 1 minute per rule and 2 threads. The job has a 20-minute
outer CI timeout. Login/logout are excluded from crawling to preserve the synthetic
session. Rate limiting may deliberately reject scanner requests with 429.

DAST HTTP transport is inside a disposable internal Docker network. HTTPS cookie,
Host/Origin rejection, session rotation/revocation and CSRF are separately exercised
by application security tests. `scripts/security/dast.sh https` additionally creates
a certificate-verified TLS proxy entirely inside a disposable container and verifies
Secure/HttpOnly/SameSite cookies, CSRF, logout/replay rejection and cleartext refusal.
It needs no host ports and writes `https.json`. An HTTP DAST run alone does not prove
HTTPS deployment.
Reports may include synthetic payloads and temporary sessions: keep artifacts private
and do not attach them to public issues without review. Temporary sessions cease
to exist when the disposable instance is destroyed.

## Targeted manual review

Before broad external deployment, a human must review the deployed configuration
against [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
and the [Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/).
The repository campaign records concrete attack attempts and re-tests; it does not
claim an independent professional penetration-test certification.

Review at least authentication/session management (ASVS V2/V3, WSTG ATHN/SESS),
authorization and direct resource IDs (V4, ATHZ), input/file handling and XSS
(V5, INPV), cryptography/secrets (V6/V9), error handling/logging (V7), data protection
(V8), and infrastructure/provider egress (V9/V14, CONF).

For each row retain the tested revision, exact safe reproduction, preconditions,
expected/observed result, impact, correction and re-test evidence. Use synthetic
identifiers, redact tokens and avoid copying business data into reports. No release
may retain a proven credential leak or a path that writes analyzed business data.

## Findings and re-test register

| ID | Area | Observation | State | Re-test evidence |
| --- | --- | --- | --- | --- |
| V19-RUNTIME-BROKER | ASVS V14 / WSTG CONF | Trivy DS002 flags the trusted runtime namespace supervisor. Only this file/rule is accepted until 2027-01-23; child non-root isolation and broker rejection checks remain release gates. | Scoped architecture exception | Require child UID/GID/capability/filesystem/network evidence from the same built image. |
| V19-REVIEW | Deployment | Human review of the final reverse proxy/HTTPS/access configuration is required before broad exposure. | Deployment gate | Run the documented access tests against the actual deployment; local tests do not certify another host. |
| V19-SAST-COVERAGE | CI | Initial rule path filters selected zero files. Removed the directory filters, scoped scan targets to production directories, and retained a nonempty-coverage gate. | Corrected | Nonempty source coverage required; final candidate scan records its file count. |
| V19-CSP | WSTG CONF / INPV | Missing API/error-route CSP, unnecessary framework identification and broad inline stylesheet policy. | Corrected and re-tested | Baseline 57 checks and bounded active scan 106 checks, zero warnings/failures; bare `/api` included. |
| V19-IMAGE-DEPS | Dependency hygiene | Outdated build tools, CLI vulnerabilities and OS package findings. | Corrected tooling; conditional OS reviews | Updated bases/CLIs, removed unused package managers/affected tools and SUID bits. Exact-image raw reports retained: backend 50, frontend 43, runtime 65 high/critical records covered by 16 expiring applicability reviews; zero unreviewed blocking findings. |
| V19-GO-OPENPGP | Dependency inventory | `GO-2026-5932` flags the `golang.org/x/crypto` module bundled in GitHub CLI, severity UNKNOWN. | Recorded below blocking threshold | The advisory concerns deprecated OpenPGP packages. SpecHelper invokes fixed GitHub login/token/user commands, not OpenPGP operations; the analysis image has no GitHub CLI. Raw inventory remains available; a future high/critical classification blocks automatically. |

## Scanner references

- [Gitleaks container releases](https://github.com/gitleaks/gitleaks/pkgs/container/gitleaks/)
- [Semgrep CLI and privacy controls](https://github.com/semgrep/semgrep)
- [pip-audit security model](https://github.com/pypa/pip-audit#security-model)
- [npm audit](https://docs.npmjs.com/cli/commands/npm-audit)
- [Trivy image scanning](https://trivy.dev/docs/latest/guide/target/container_image/)
- [ZAP baseline](https://www.zaproxy.org/docs/docker/baseline-scan/),
  [active scan](https://www.zaproxy.org/docs/docker/full-scan/) and
  [scan hooks](https://www.zaproxy.org/docs/docker/scan-hooks/)
