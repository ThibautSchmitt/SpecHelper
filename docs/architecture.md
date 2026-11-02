# Architecture

Conversation records reuse `Request`; each independently frozen investigation uses
an `AnalysisRun` and immutable `ResultVersion`. `ConversationTicket` stores each
editable ticket with an optional exact result, selected-message anchor and bounded
context references. Drafting uses this scope instead of the entire conversation.
Destination-specific previews remain `TicketPublicationDraft`; publication records
retain the prepared-ticket identity when known. The former selected preparation
JSON remains mirrored for compatibility, but it is not the identity of every ticket.
Reading or saving a preparation does not enqueue work. Row locks and revision guards
prevent stale saves or a delayed drafting response from overwriting another ticket.
Tickets browsing reads individual `PublishedTicket` records only when their status is
confirmed and an external identifier or reference exists. Its small projection excludes
bodies, drafts and operational histories. Saved URLs are rechecked against the connection
origin and supported provider ticket routes without contacting the provider; missing or
unsafe links are not reconstructed. Drafts and operation details remain available from
the conversation. Reconciliation only searches for the
original external reference. A retry of a definitively rejected operation records its
previous outcome in `PublishedTicket.attempt_history` before claiming another attempt.
Published snapshots remain immutable, including when their source conversation is archived.

Both destination drafts and publications may reference a conversation ticket without
an analysis result; database constraints require at least one real source. No placeholder
analysis row is created. Prepared-ticket publication bypasses the legacy completed-change
analysis gate while retaining environment permissions, provider validation, immutable
payload hashes, idempotency and explicit human confirmation. Incomplete verification or
changed content requires a separate strict acknowledgement. Legacy result-only publication
keeps its original verification rules.

A confirmed write records one durable `ticket_publication` message under the conversation
lock, keyed by publication ID. The timeline renders the persisted publication once at its
completion time; failed and uncertain writes do not create success messages. Natural ticket
requests use the normal conversational turn and optional structured draft output. Ambiguity
asks one question and retains bounded context for the answer; it does not enqueue deep roles.

SpecHelper separates conversational exploration from independently checked analysis.
Both use the same conversation history and authorized resources. This describes the
implemented reference deployment, not a proposed architecture.

## Services and runtime

The [Compose file](../compose.yaml) is the deployment authority.

| Component | Responsibility |
| --- | --- |
| Frontend | Next.js/React UI and same-origin proxy to the backend; only published host port |
| Backend | Django/Ninja API, access checks, configuration, stored conversations, results and publication |
| Application PostgreSQL | Durable application records, task queue, reservations and transaction locks |
| Worker | Queue admission, checkpoint orchestration, runtime gateway and supervision of independent job subprocesses |
| Agent runtime | CLI execution, encrypted AI credentials, sessions, constrained resource brokers and sandbox children |
| CLI maintenance | Explicit CLI installation/update outside analysis children, coordinated with active work |

One-shot storage services establish volume ownership and control secrets. Sources,
frozen workspaces, reference documents, uploads, credentials and native session data
have distinct persistent volumes. Backups must keep them consistent with application
PostgreSQL and encryption keys; see [Installation](installation.md#backups-and-recovery).

The backend's two HTTP processes are not analysis workers. A single worker supervisor
can start several independent job subprocesses. A queued request is not evidence that
it is already running, but the deployment is not restricted to one sequential analysis.

## Conversation and analysis state

Existing request records hold the need, ordered messages, environment and discussion
state. Jobs record execution state and bounded observations. Analysis runs, role steps,
AI sessions and result versions preserve checkpoints and provenance. Publication
records retain the chosen destination and uncertain/confirmed outcomes.

The four conversation states are derived from actual queued/running jobs and pending
clarifications: discussion, in progress, waiting for AI, and reply expected. Terminal
job/run states remain unchanged. A failed/cancelled operation or an orphaned active
technical state adds a visible incident; it is never silently shown as still running.
`archived_at` controls the active/archive filter independently of execution state.
Archiving changes neither messages, native sessions, results nor publication evidence.
Deletion remains soft and retains published-ticket provenance.

A new discussion selects one eligible AI connection and keeps its model and session.
The application persists the visible history independently of native CLI storage.

| CLI | Native discussion continuation |
| --- | --- |
| Codex | Resume the recorded thread through `exec ... resume` |
| Claude Code | Resume the recorded session with `--resume` |
| Antigravity | Continue the recorded conversation with `--conversation` |

Continuation depends on retained session files, provider support and matching execution
configuration. A missing/invalid session triggers explicit recovery with bounded saved
context and a new native session. The application does not call this an unchanged
session or silently switch providers. Session directories and execution contexts are scoped
to the conversation and environment; there is no shared cross-conversation memory.
The UI retains recorded connection/model/reasoning history. A user-confirmed transfer
after quota exhaustion creates a new native session with bounded saved context; it
does not migrate the provider's private session state. See [Usage](usage.md#start-a-discussion).

**Launch deep analysis** asks for the subject and relevant user messages, then captures
a separate need and resource baseline for each cycle. Its frozen dossier contains
only those selected exchanges and that cycle's subsequent answers/decisions. Other
cycles' conclusions are not injected as verified facts. Old results remain accessible
and the discussion session is retained. Human
statements and confirmed decisions are distinguished from exploratory AI hypotheses.
The discussion's native session is never reused as an Analyst or Counter-analyst session.

Within one deep cycle, the roles execute sequentially:

1. The Analyst investigates authorized evidence.
2. The Counter-analyst starts independently of the Analyst's conclusions, then confronts them.
3. The Validator checks the findings, evidence and unresolved material issues.

Role sessions remain distinct even under a permitted same-family fallback; separate
sessions do not establish provider diversity. Any role can pause for a clarification.
Factual answers are conversation context, not automatically normative business decisions.
Technical access failures remain execution errors. Accepted results retain their need
version and references; later discussion cannot retroactively verify or rewrite them.

Progress guards reject repeated/empty transitions and incomplete mandatory checks.
A finished execution can produce a partial result. Publication requires the existing
verification and human-preview gates, not merely an execution-completed status.

## Parallel work and cancellation

Admission uses short PostgreSQL transactions and row locks, including
`select_for_update(skip_locked=True)` for task claiming. Long CLI work runs outside
those locks. Independent conversations share configurable account and instance slots:
by default **four per account and eight overall**. Discussion and deep-analysis calls
use the same budgets. Account aliases share reservations for the detected account.
One conversation permits only one active operation at a time.
AI invocations use a one-hour execution limit by default, including conversational
turns, library drafting and deep-analysis checkpoints. Runtime validation and the
Antigravity CLI accept the same bounded limit. Database/network tool limits remain
separate. An explicit retry applies the current invocation budget and records the
change without replacing frozen evidence, role sessions or completed checkpoints.
An execution timeout is reported explicitly; it never becomes successful verification.

The roles inside an analysis remain sequential while other conversations run alongside
it. Actual provider throttling, quota, authentication and backoff still constrain work.
A waiting job does not reserve all future roles. Native sessions and checkpoints remain
associated with their own request and attempt.

Cancellation identifies the exact runtime attempt. A reservation is retained until
that attempt is known to have stopped; stale completion cannot release another job's
slot. Interrupted jobs recover from recorded state. Configuration changes and CLI
maintenance coordinate with all active invocations, including pending stops.

The reference agent container shares two CPUs, 2 GiB memory and 256 process slots.
Raising admission limits does not add provider capacity or host resources. The HTTP
request limiter is a different mechanism. SQLite development tests do not prove
PostgreSQL locking or multi-process concurrency; use disposable PostgreSQL tests.

## Work observations and browser updates

Adapters consume structured provider events and project safe tool lifecycles,
public messages and eligible response fields into common observations. Provider
coverage differs; neutral processing remains correct when no useful event arrives.
Private reasoning, raw commands, credentials and unrestricted tool output are excluded.

A turn receives an immediate acknowledgment before the CLI's first event. Each execution
updates one expandable progress element. Deep analysis adds the real role states.
Selected user-facing response prefixes can appear as drafts pending validation; an
incomplete JSON object is never rendered as a final answer.
Terminal cycles stay anchored to their recorded cycle/step timestamps rather than
following later discussion inputs. Reopening the page preserves that ordering.
The conversation and Activity share one clock for AI execution in the current retry.
Explicit retries reset that clock; prior attempts and resource/clarification waits are
excluded. Recorded step intervals remain available in history. A running clock advances
locally between polls and stops when execution pauses, ends or tracking becomes unavailable.
Persistent Antigravity turns require a native `finish` completion after the current
input. A cached structured result without that completion is rejected and is not
shown as a draft or saved as a new reply. Equal response text alone is not an error.

The worker/runtime exchange structured execution observations. The browser uses narrow,
cursor-based polling, normally every two seconds during active work and ten seconds
when idle. This is not an SSE or WebSocket implementation. Bounded observations persist
in jobs for reload/history, rather than retaining an unlimited terminal log. Tracking
failures are distinguished from provider failures. Auto-scroll follows only readers
already near the bottom of the conversation.

## Sources, documents and database observations

Git connections maintain mirrors and authorized checkouts. Analysis workspaces retain
frozen SHAs; branch movement does not rewrite previous conclusions. Environment facts,
reference documents and attachments have captured versions and read-only sandbox bindings.
Path bounds, signatures and hashes prevent substitution with unrelated host files.
Removing a current reference does not erase copies retained by historical analyses.

The optional business PostgreSQL connection is separate from application storage.
It is accessed through a constrained read broker with a dedicated reader, read-only
transactions, query validation, timeouts and result limits. A captured connection is
not a database snapshot. Evidence describes the rows and observation period actually
read, not all possible records or a live UI session.

Publication credentials live in a global connection catalogue. A many-to-many relation
associates connection IDs with environments; it never duplicates credentials. The old
single-environment column is retained only as migration/compatibility data and grants
no publication access. The association and enabled/verified status are checked at
preview and again under row locks when admitting a new write. Immutable publication
records retain their original connection and destination. Changing accounts cannot
silently reconcile another account's operation.

Ticket publication is a separate backend operation. Agents cannot write business data
or publish tickets through their resource tools. Destination credentials, preview edits,
templates, attachments and uncertain-write reconciliation have their own validation.

## Trust boundaries and implementation pointers

Analyses and activity are shared across browsers after instance access checks. Browser
cookies provide attribution, not per-conversation authorization. Native sessions belong
to a conversation; row locks and revision guards serialize its operations. Distinct
conversations and deep-analysis roles retain separate contexts. This is not
individual-account authentication or tenant administration. Access settings,
AI connections and deployment administrators remain trusted. The runtime supervisor
needs namespace privileges; its analysis children run as a separate non-root identity
with restricted mounts, network access and capabilities. See [SECURITY](../SECURITY.md)
for the complete boundaries and residual risks.

| Area | Source |
| --- | --- |
| API and data | [backend/core](../backend/core) |
| Shared conversation access and browser attribution | [discussion_access.py](../backend/core/discussion_access.py) |
| Persistent discussion | [discussion.py](../backend/core/discussion.py) |
| Explicit discussion transfer and AI history | [discussion_continuation.py](../backend/core/discussion_continuation.py) |
| Built-in procedures and mandatory instructions | [builtin_skills.py](../backend/core/builtin_skills.py), [native_policy.py](../backend/core/native_policy.py) |
| Background environment branch checks | [branch_checks.py](../backend/core/branch_checks.py) |
| Queue supervision | [management commands](../backend/core/management/commands) |
| CLI adapters and sandbox | [runtime](../runtime) |
| Conversation and progress UI | [frontend/src](../frontend/src) |
| Publication adapters | [ticket_providers.py](../backend/core/ticket_providers.py) |

The optional indexing experiment is evaluation tooling, not the production navigation
path. Recorded quality limits are in [Qualification evidence](evidence/qualification.md).
