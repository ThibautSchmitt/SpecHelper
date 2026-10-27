# Architecture

The established application baseline is v2.5 with the current
[Antigravity adapter](antigravity.md). [Analysis](analysis.md) is the reference for
execution and evidence; [operations](operations.md) owns deployment, backups and
runtime commands. Read [SECURITY](../SECURITY.md) before remote exposure.

## Services and runtime

| Service | Purpose |
|---|---|
| frontend | Next.js / React / TypeScript, shadcn/ui components and Tailwind tokens |
| backend | Django / Django Ninja, configuration and business API |
| worker | Persistent PostgreSQL queue, synchronization and analyses |
| database | Application data, separate from analyzed business databases |
| agent-runtime | Codex CLI / Claude Code / Antigravity CLI, isolated on Linux with Bubblewrap |

One Git mirror per remote supplies detached worktrees. Named sources use a stable
provider/instance/remote identifier, independent of account and branch. Mirror locks
serialize access across configurations. Environment worktrees are separated by SHA
generation and branch selection; legacy worktree paths remain compatible. Request
worktrees are separate. Launching a request freezes its SHAs and database selection;
retained commit refs preserve its baseline across later fetches and force-pushes.

An agent receives its read-only request workspace, attachments, explicitly allowed
frozen context files and authorized repository history, plus its own writable session directory. Shared
Git caches expose only those repositories' objects and the current worktrees' metadata;
other repositories and other jobs' linked-worktree metadata remain hidden. Repository
history is available for analysis; result citations are checked against frozen SHAs. It
cannot access application data, real Git/AI/database credentials or other request
sessions. The trusted runtime supervisor needs `SYS_ADMIN`/`NET_ADMIN` for namespace
setup. The child runs as UID/GID 10001 with zero capabilities, no-new-privileges and
an inherited syscall filter. `init: true` reaps orphaned Bubblewrap children.
Isolation or syscall-filter failure stops execution. See the
[threat model](threat-model.md) for the supervisor's residual host privileges.

Bubblewrap provides the effective sandbox. Codex's internal sandbox is disabled inside that isolation to avoid conflicting namespaces. Linux still mounts sources, cache and attachments read-only. The default Codex model is GPT-6-Luna, configurable through `CODEX_MODEL`. Understanding uses low reasoning effort and technical analysis medium effort. These settings remain internal; users simply connect their ChatGPT account.

Compose networks separate the runtime from the frontend, backend and application
database. The worker reaches it through an internal control network; the backend
uses a restricted authenticated control relay. A separate per-run Unix broker
injects real provider credentials into a fixed upstream endpoint allowlist. The child
receives only a synthetic expiring capability and a loopback relay in an isolated
network namespace. Provider calls cannot select arbitrary destinations or follow
redirects. Source/reviewer steps may separately request bounded public HTTPS references
through the Web reader, with validated/pinned DNS and redirect revalidation. No
provider credentials or caller-controlled headers are forwarded to public pages.
A request-scoped database capability uses the same broker. Internal
keys and encrypted CLI credentials are outside the child's mounts.
See [official references](analysis.md) for conditional research, transfer
limits, actual page receipts and applicability boundaries.

The optional business database is accessed through a request-scoped temporary capability, PostgreSQL parser, function allowlist and read-only transaction. Owner, superuser, write-enabled and object-creation roles are rejected. Queries are limited to five seconds and 200 observed rows; AI previews are further minimized to 20 rows with bounded, masked cells. Credentials never enter prompts. A database baseline identifies the connection; it is not a data snapshot.

Allowed attachments are PNG/JPEG/GIF/WebP, PDF, DOCX, TXT, Markdown, CSV, JSON and
LOG, up to 25 MB each and 20 files per request. Actual signatures and streamed sizes
are checked. DOCX ZIP expansion/entry/depth limits reject macros, traversal and
embedded executable content; other archives are refused. Random internal names
isolate files outside public directories. Document readers run inside the bounded
analysis namespace; documents are untrusted data, not permission grants.

## Persistent execution and history

`Request` holds requests and questions through its workflow discriminator. `Job`
persists queue state, `AnalysisRun` records an execution, and `StepExecution` stores
checkpoint attempts, leases, snapshots and outputs. `AISession` isolates role/provider
contexts. Result versions and artifacts are immutable; follow-ups append versions.
`QuestionDocument` and source-version links retain exported question context.
`TicketPublicationDraft` stores mutable revisions separately from immutable results;
`PublishedTicket` retains reviewed payloads, exact source versions, operation keys
and per-file delivery state.

A worker supervises step subprocesses. PostgreSQL row locks and quota-group leases
coordinate claims across workers; SQLite development is not evidence of production
concurrency. The queue API only reads persisted jobs. Backend control requests use
the authenticated worker relay; runtime execution is worker-only.

New work retains protocol identifier `2.4`; v2.5 adds behavior without replacing
that contract. Historical running work keeps its old contract. Marked older pending
analyses transition at claim while retaining IDs, baselines and audit snapshots;
insufficiently qualified reports are rechecked. Preserve historical migrations.

## Frozen environment resources

Business terminology, factual context and immutable document versions belong to an environment. They are untrusted documentary data; configurable instructions belong only to the global settings and the selected AI connection.
Each launch records a logical manifest with content hashes, Git baseline, business
answers and request-specific attachment references. Clarification keeps the same
reference versions while recording the new answers. A later discussion uses the
current environment references and retains the original Git baseline.

Reference originals live in `app-data/context-resources`. Verified copies use the
separate `analysis-context` volume, writable by the backend/worker and read-only
in the runtime. Bubblewrap binds only the allowlisted files under `/context`.
Removing a resource or deleting an environment keeps historical versions and
request-scoped downloads. No document bodies are inserted into the initial prompt.

Linux `IN_ACCESS` observation records reads of the frozen files by document version
and public role. Validation runs before observation starts; downloads read separate
original files. An observed read does not prove comprehension. Missing observations
do not prove that a resource was unused: memory-mapped reads may be missed, and
unsupported kernels or event overflow report telemetry as unavailable. Positive
observations survive later calls and failures.


## Interface and source layout

The shell keeps Home, Analyses and Tickets in the sidebar, Settings at the
bottom left, central content and the task panel. Small screens use drawers.
EN/FR catalogs supply fixed strings; frozen analysis language reaches every role.

The unified read/creation API reuses existing Question/Request records and services.
Historical routes remain valid. A small additive `intent_mode` field distinguishes
automatic initial classification from historical explicit workflows; it does not
rewrite existing histories. Need revisions and retry-safe linked transitions append
business events under the dossier lock. Result, decision and need revisions fence
edits; immutable results retain their own context, baseline and evidence.

Explanatory diagrams are bounded structured node/relation proposals. The independent
verifier reviews each relation, and the service accepts existing relations only with
supported Git/SQL claims. The service generates Mermaid rather than accepting arbitrary
rendering directives. Reviewed proposals, reviews and textual sources are stored in
the immutable evidence JSON. The frontend loads Mermaid on demand, renders in strict
mode and displays an image document with a textual fallback. External diagram annexes
reuse the existing selected-byte hashing and once-only attachment delivery contract.

| Directory | Responsibility |
| --- | --- |
| `frontend/src` | Next.js routes, components, theme, translations and API client |
| `backend/core` | Models/API, Git/context, scheduling, evidence and publication |
| `runtime` | Trusted supervisor, constrained child, brokers and isolation probes |
| `scripts/evaluation` | Synthetic source/index/native evaluation; no production index |
| `scripts/security`, `security` | Disposable scans, rules and explicit findings |

See [threat boundaries](threat-model.md) for credentials, provider transfers and
residual privileges. Database and public research are optional scoped capabilities.
