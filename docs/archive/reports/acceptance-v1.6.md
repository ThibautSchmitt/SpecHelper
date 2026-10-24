> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v1.6 environment context acceptance — October 22, 2026

## Functional coverage

| Area | Implemented behavior | Evidence |
|---|---|---|
| Optional environment context | Short instructions, independent activation, shared document references and existing request attachments remain separate | `test_v16_context.py`, `test_v16_flow.py`, `v16.spec.ts` |
| Administration | Upload, replace, disable, remove, metadata, bounded text preview, unreadable text, revision conflicts and 20 × 25 MB limits | Storage/API tests and desktop/mobile browser checks |
| Frozen manifests | Request, answers, environment, Git SHAs, optional read-only database selection, active resource versions/hashes and attachment references | Queue/flow tests; source synchronization and migration checks |
| Clarification and continuation | Clarification retains document references while recording new answers; subsequent discussion uses current references and retains Git SHAs | Queue/flow and actual Linux workflow checks |
| Historical access | Old result content and document versions survive replacement, removal and environment deletion; downloads require membership in the selected run | Storage/API/flow tests and Linux workflow checks |
| On-demand exploration | Only short instructions and file metadata enter prompts; long files remain available through verified, individually allowlisted read-only mounts | A 300 KB Linux resource check; complete workflows with a reference exceeding 300 KB |
| Independent roles | Analyst, counter-analyst and verifier get identical frozen references and distinct private sessions; initial counter context excludes analyst conclusions | Flow tests, dual-provider Linux workflow and independent-session smoke |
| Checkable conclusions | Typed evidence, impacts, risks and uncertainties are persisted; stale/conflicting references must be flagged and actual code takes precedence | Generic preset and role instructions, typed flow tests and deterministic stale-document scenario |
| Read observations | Actual Linux file reads are recorded by version and role; missing or unavailable telemetry is explicitly distinguished | Inotify tests, real Bubblewrap smoke and request-version browser checks |
| Credentials | Configured credentials rejected in instructions/text references; exact configured secrets redacted from prompts, typed outputs and published artifacts | Credential-boundary tests; database runtime smoke; publication credential scan |
| Generic projects | Current preset discovers stack/dependency conventions without built-in framework rules | Real Git Python/TypeScript fixtures and actual Linux workflows for both stacks |
| Preserved boundaries | Source, cache, context and attachment writes denied; business SQL read-only and bounded; no code or pull request creation | Existing isolation, source workflow and PostgreSQL gateway checks |

## Verification

- Backend: **348 passed, one skipped** using disposable PostgreSQL 17, including business-database integration. The skipped test is Linux-only on the macOS host; Linux observation is exercised inside Docker.
- Browser: **64 desktop/mobile scenarios passed**, including six new context scenarios, both languages, historical versions and the actual API-backed attachment/clarification/export fixture workflow.
- Two additional desktop/mobile checks passed on the deployed instance, including the French context form without horizontal overflow.
- Production frontend build and TypeScript passed. Ruff, migrations and Compose configuration passed.
- Linux context smoke: 300 KB document read; only the read resource reported; source writes, new context files, other requests and other sessions unavailable.
- Full deterministic Codex workflow: clarification, same-session resumption, document replacement, unchanged historical result, recorded reads and SHA export.
- Full deterministic TypeScript workflow: Codex/Claude confrontation, independent role contexts, shared frozen references, replacement/history and exports.
- Full deterministic Claude/PostgreSQL workflow: source/context reads, allowed database SELECT, denied DELETE, credential exclusion and capability expiration.
- These workflows use terminal stand-ins inside real Bubblewrap isolation. Their short durations measure application plumbing, not AI-provider latency or model quality.

## Migration and deployment

A protected PostgreSQL backup was restored to a disposable database. Migrations
0017–0018 passed there and on the deployed instance. Thirteen historical model
fingerprints matched before and after both migrations and again after acceptance
cleanup. Old results and artifacts were not rewritten. The bundled framework
preset becomes generic project conventions; customized instructions and connection
skill overrides remain preserved.

An actual backend-to-runtime volume test verified that a backend-created reference
can be read through the deployed readonly mount and that its access is recorded.

The dedicated `analysis-context` volume carries only frozen document copies to the
runtime. It is mounted read-only there; original references and application data
remain outside the agent sandbox. All five Compose services were checked after
the upgrade. See [environment context](../guides/environment-context.md) for administration,
retention and observation limits.

## Connected-account limit

Two isolated source fixtures were queued for actual ChatGPT analysis. The provider
returned `QUOTA_EXHAUSTED` before producing an analysis. Both disposable requests
and their fixtures were removed without altering existing user requests or source
environments. The observed quota state was preserved; it was not reset to pretend
that capacity was available. No real-model analysis quality is claimed for this
release. Deterministic scenarios establish the context transport, workflow,
versioning, isolation and output contracts.

Read telemetry proves an observed access, not comprehension. Memory-mapped reads
may be missed; unsupported kernels or lost events explicitly report incomplete
telemetry. Exact configured-secret redaction is not general-purpose data-loss
prevention. Corrupt or encrypted documents may still be unreadable despite their
supported extension.
