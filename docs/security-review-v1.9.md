# v1.9 targeted security review

Date: 2026-10-23. Scope: repository implementation and disposable reference Compose
deployment. Method: agent-assisted source review, explicit attack attempts, real TLS,
browser regressions, native CLI protocol checks and bounded ZAP scans. This is a
tracked targeted assessment, not an independent human penetration-test certification.
Private artifacts contain synthetic scan traffic or redacted evidence and stay out
of Git. No active scan targeted the team's running instance or business databases.

## Review and reproducible evidence

| Area | ASVS / WSTG reference | Attempt and expected boundary | Observed result |
| --- | --- | --- | --- |
| Anonymous access and resource IDs | V2/V4; ATHN/ATHZ | Read existing/missing requests, attachments, result exports, Settings and API documentation before login | Identical 401 responses before resource lookup; no business content. All authenticated sessions retain equal shared-team permissions. |
| Sessions and transport | V3/V9; SESS/CRYP | Use actual certificate-verified TLS; login, retain the old session, logout and replay it; try cleartext authentication | Secure/HttpOnly/SameSite Strict cookies; CSRF rotation at login, old session rejected after logout, cleartext refused. `scripts/security/dast.sh https` produces the evidence. |
| CSRF and origins | V4/V5; SESS/INPV | Omit CSRF on login/logout/updates, send a hostile Origin, change Host, try malformed origins | Rejected; hostile update leaves Settings unchanged. Unit tests also cover malformed forwarded/local-host and origin syntax. |
| Rate/concurrency and audit | V7/V14; CONF/SESS | Exceed login/read budgets, hold a concurrency lease, inject content into errors/log paths, expire security records | Shared database budgets reject excess requests; logs/audit omit supplied content and secrets; cleanup leaves business rows unchanged. |
| Hostile files and downloads | V5/V8; INPV | Upload disguised executables, conflicting signatures, ZIP traversal/macros/high compression, false sizes; request another attachment path or a symlink target | Rejected before ingestion or confined to the owning request storage. PDF text extraction executes inside the non-root read-only analysis namespace. |
| Browser output | V5; INPV | Render script tags, event-handler images, JavaScript links and external tracking images from ticket Markdown | No script execution, unsafe link or remote image fetch; text remains safely rendered. Desktop/mobile browser tests pass. |
| Secret lifecycle | V6/V8; CRYP/CONF | Wrong vault key, modified ciphertext, failed atomic replacement, symlink/oversize credential, OAuth refresh racing a newer login | Fail closed or preserve the newer login. Real legacy credential copies sealed with identical decrypted bytes; temporary status files are private and removed. |
| Git read/write separation | V4/V14; ATHZ/CONF | Fetch a changed branch through the Git service; retain the old request SHA/worktree; attempt writes from analysis | Real Git mirror/worktree regression preserves the old baseline. Linux analysis cannot write source files and has no Git credentials or arbitrary remote connection. |
| PostgreSQL source privileges | V4/V5; ATHZ/INPV | Disable client READ ONLY and attempt DELETE/CREATE using the reader; grant table/column write or CREATE; test an owner/superuser; read over 200 rows | PostgreSQL permissions reject writes even without client protection; adapter rejects privileged roles; response truncates to 200. Tests use only a disposable PostgreSQL fixture. |
| Runtime containment and indirect injection | V14; CONF | Attempt source/other-session/credential writes and reads, arbitrary TCP, unauthorized broker endpoints, unshare/ptrace, and injected instructions carried by README/PDF/ticket/DB | UID/GID 10001, zero capabilities, no-new-privileges and seccomp enforced; all forbidden attempts denied. The harness measures material permissions, not an LLM injection-resistance percentage. |
| Provider interoperability | V9/V14; CONF | Run installed native Codex/Claude with synthetic credentials against a controlled upstream rejection | Only selected provider endpoints reached, real synthetic upstream token injected outside the child; unauthorized endpoint denied. Current Claude's structured 401 is classified as an authentication error. No paid inference performed. |
| Automated external-style probes | V5/V14; INPV/CONF | Authenticated ZAP baseline and bounded active scan against disposable services | Baseline: 57 checks, zero warnings/failures. Active: 106 checks, zero warnings/failures. Findings apply only to the crawled/seeded target and configured duration. |

## Corrected findings

- Shared remote access was previously unguarded: password/session middleware now
  gates business and administration APIs before lookups and validates CSRF/Host/Origin.
- CLI credential files and per-session copies exposed reusable OAuth: vault storage
  and a credential-injecting provider broker replace analysis-readable real credentials.
- The analysis identity previously retained excessive privileges/network reach:
  distinct UID/GID, capability removal, seccomp and a private network namespace enforce
  the boundary independently of prompts and native model permission decisions.
- Upload metadata was insufficient: actual type/size and bounded DOCX inspection now
  reject mismatches, executables, macros, path traversal and compression abuse.
- GitHub issue publication reused source access: a dedicated publication credential
  is now required and reused repository credentials are rejected at configuration
  and GitHub adapter execution.
- SAST initially selected no source: target scoping and nonempty-coverage validation
  now prevent an empty successful-looking report.
- ZAP found missing API CSP, broad inline stylesheet policy and framework identification:
  API responses including errors have restrictive CSP, stylesheet elements require
  same-origin sources, and the framework identification header is disabled. Re-tests
  show no remaining baseline/active findings in the tested scope.
- Image scans found outdated build tooling and Claude Code vulnerabilities: unused
  package managers were removed, Python/Node base images refreshed, GitHub CLI installed
  from its signed upstream repository and Claude updated to 2.1.309. Raw image reports
  remain available alongside the exact-image applicability assessments.

## Conditional OS findings and residual risk

The distribution scanner still flags OS source packages. Each review in
[`image-applicability.json`](../security/image-applicability.json) lists the exact
package URL, component, source advisory, reason, required checks and expiry. Examples
are unused infocmp/Archive::Tar code, absent homed/TPM/X11/tiffcrop services, and
privileged mount paths prevented by removed SUID bits and the analysis boundary.
No application-package finding is covered by these reviews. Any newly available
distribution fix, package identity change, missing condition or expiry blocks the
gate and requires another review. The GitHub CLI entry records the upstream-fixed
vendor binary instead of incorrectly treating Debian's source-package flag as proof
that this newer binary is still affected.

The complete image inventory also records the UNKNOWN-severity
[Go OpenPGP deprecation advisory](https://pkg.go.dev/vuln/GO-2026-5932) on the module
bundled in GitHub CLI. The affected OpenPGP operations are outside SpecHelper's fixed
login/token/user command path, and GitHub CLI is absent from the analysis image.
This is recorded below the high/critical gate, not hidden as a clean dependency scan.
Other lower-severity distribution records remain in the raw inventories; broad
distribution maintenance and host exposure must be reviewed independently.

The libtiff sample-count denial of service is a conditional mitigation, not a claim
that the vulnerable library is absent: TIFF uploads are refused, document decoding
is confined to the resource-limited child, and job-level denial of service remains
possible. Host resource monitoring and a dedicated runtime host/VM remain important.
Trusted supervisors, administrators and provider accounts are outside the child
sandbox's trust boundary. Never extend these reviews to a custom privileged or
host-networked deployment without re-testing their prerequisites.

An operator must still review their actual reverse proxy, TLS termination, firewall,
kernel/container policy, backup access and provider retention before broad remote
exposure. No local or automated report certifies another deployment or guarantees
the absence of vulnerabilities.
