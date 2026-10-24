# Known limitations and open work

This register retains active limitations from historical reviews. Passing an archived
test certifies neither a current installation nor every model response. Reviewed 2026-10-24.

| ID | Current limit | Consequence / evidence still needed |
| --- | --- | --- |
| REL-01 | The v2.3 native comparison failed exact-source proof: 6/29 final citations and 26/87 across all roles had excerpt/range defects. | Production indexing stays disabled. Fix citation extraction/validation and repeat an independently reviewed representative study before activation. |
| REL-02 | Three tiny synthetic projects, one model family, one ordered run and variable cache usage do not establish representative quality or performance. Billing was absent. | No accuracy percentage, index benefit, token savings, throughput or measured cost claim. See [evaluation](index-evaluation.md). |
| REL-03 | Controlled responses prove protocol behavior, not exhaustive coverage or correct live interpretation. | Review material conditions, omissions and counterexamples; unresolved limits remain partial. |
| DATA-01 | PostgreSQL baseline identifies a connection, not frozen data; absent access means no real-record validation. | Record period, population, configuration, sampling and unavailable access. Finite observations do not prove universal claims. |
| DATA-02 | File-read telemetry proves access, not comprehension; mmap, kernel support and event loss can leave gaps. | Distinguish unavailable/incomplete telemetry from non-use. |
| DATA-03 | Exact credential redaction is not general confidential-data detection; public URLs/search disclose submitted terms or paths. | Review submitted/exported content. The public reader is not semantic data-loss prevention. |
| AI-01 | Claude standalone quota/model discovery is not validated here; metadata does not prove subscription entitlement. | Keep unknowns explicit and verify actual authorized use. |
| AI-02 | Fresh contexts do not create family diversity; authentication alone does not clear exhaustion. | Preserve role eligibility, explicit fallback/waiting and quota leases. |
| TK-01 | GitHub Issues attachment upload is unavailable through supported APIs here; v2.5 upload evidence uses controlled transports. | Do not claim live vendor upload validation. The actual disposable GLPI 11.0.7 creation/reconciliation trial predates uploads. |
| TK-02 | Remote writes can succeed despite lost responses; search may be delayed. | Reconcile uncertain issues/files and inspect the destination; never blindly repeat writes. |
| WEB-01 | Some official sites need unsupported formats/authentication; provenance does not certify applicability. | Report unavailable/unknown research. Web evidence alone cannot prove deployed behavior. |
| SEC-01 | Trusted supervisor retains namespace privileges and relaxed container profiles; host administrators are trusted. | Use a dedicated host/VM and retest [boundaries](threat-model.md). |
| SEC-02 | Session monitoring is not an atomic filesystem quota; bounded decoding denial of service remains possible. | Monitor resources. TIFF refusal and isolation mitigate risk without proving the library absent. |
| SEC-03 | Image OS findings have exact, expiring applicability reviews; UNKNOWN Go/OpenPGP findings remain recorded. | Review current packages, raw scans, expiry and same-image controls. Images are not claimed vulnerability-free. See [security validation](security-testing.md#findings-and-re-test-register). |
| SEC-04 | Local automated review is agent-assisted, not an independent professional pentest. | Review actual TLS, firewall, kernel, backups and provider retention before broad exposure. |
| OPS-01 | A source push or clean startup does not upgrade an existing team instance. | Rehearse migrations and report deployment/remote CI separately. |
| SCOPE-01 | One trusted team shares equal access and capacity; no individual accounts, private spaces or tenancy. | Do not host mutually untrusted teams together; capacity can delay work across browsers. |
| SCOPE-02 | Source modification, PRs, business DB writes, production Copilot/Antigravity/local models and cross-request knowledge are not delivered. | [Future scope](roadmap.md) adds no current capabilities. |

[Historical evidence](archive/README.md) retains original decisions, incidents and
measurement boundaries. Resolve a limitation with actual evidence and a changelog
entry; do not erase its history.
