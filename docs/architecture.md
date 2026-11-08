# Architecture

## Ticket views and analysis deliverables

One centered creation modal owns title/Markdown editing, explicit AI revision
acceptance, destination metadata and optional document choices. Its publication
action generates selected missing/outdated documents and then requires explicit
confirmation before an external write. Destination changes retain their validation
and reconciliation rules. Deep analysis can be launched through the shared editable
need dialog after saving the draft; completion does not rewrite that draft.

`core/deliverables.py` renders read-only Markdown from a selected saved ticket,
immutable result or recorded interrupted-cycle findings. Report APIs scope every ID
to its conversation and retain verification limits. Audience-specific source annexes
reuse recorded receipts and frozen Git/document material. They never execute agents
or business SQL. The common Markdown reader supplies view/download controls for
business reports, technical reports and optional `goal.md`.
`core/ticket_documents.py` separately uses the existing discussion queue to write
selected ticket attachments from the final destination draft and bounded retained
context. Matching documents are reused individually. This writing step starts no
independent analysis or business query, and it does not make new requirements verified.
Generated files, source IDs and context fingerprints remain in existing job/artifact
records; no separate document-management architecture is introduced.

Conversation records reuse `Request`; each independently frozen investigation uses
an `AnalysisRun` and immutable `ResultVersion`. `ConversationTicket` stores each
editable ticket with an optional exact result and retained context references.
A partial unique constraint permits one `active` ticket per conversation. Request row
locks serialize preparation and explicit replacement. Confirmed publication releases
that active slot; errors and uncertain writes retain it. Migration keeps all old
records, preferring an unresolved publication or existing working draft for the slot.
Retired records are retained technical history, not a user-facing draft archive.

Drafting resumes the conversational native session. A bounded recent-history supplement,
the current editable document, authorized reference files and candidate analysis results
help it identify relevant additions without a subject-selection engine. Fresh document
manifests do not move pinned Git references or reset native sessions. New initial
content is saved directly. Updates are kept in one proposal within the existing draft
JSON and require an explicit apply/discard choice with a base-revision guard.
Destination-specific previews remain `TicketPublicationDraft`; publication records
retain the prepared-ticket identity when known. The former selected preparation
JSON remains mirrored for compatibility, but it is not the identity of every ticket.
Reading or saving a preparation does not enqueue work. Row locks and revision guards
prevent stale saves or a delayed drafting response from overwriting another ticket.
Tickets browsing reads individual `PublishedTicket` records only when their status is
confirmed, `removed_at` is null and an external identifier or reference exists. Its small projection excludes
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
requests use the normal conversational turn and optional structured draft output; an
existing draft receives a reviewable proposal rather than another active document. Ambiguity
asks one question and retains bounded context for the answer; it does not enqueue deep roles.

SpecHelper separates conversational exploration from independently checked analysis.
Both use the same conversation history and authorized resources. This describes the
implemented reference deployment, not a proposed architecture.

## Services and runtime

The [Compose file](../compose.yaml) is the deployment authority. The optional
[HTTPS override](../compose.https.yaml) adds Caddy; see [HTTPS setup](https.md).

| Component | Responsibility |
| --- | --- |
| Frontend | Next.js/React UI and same-origin proxy to the backend; published directly only in local HTTP mode |
| Caddy (optional) | HTTPS entry point, persistent certificates, HTTP redirect and forwarding to the private frontend |
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
Conversation deletion remains soft and retains published-ticket provenance. Deleting
one analysis cycle follows the separate retirement path below.

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

**Deep analysis** opens a centered modal with one editable need. Opening it is read-only:
an optional structured hint saved with a conversational reply can prefill the need;
historical records use a conservative literal fallback. An isolated acknowledgement
or an ambiguous follow-up leaves the field empty.

Explicit launch reuses the existing discussion queue and native session for a short
context-selection turn, before queuing the independent analysis. It supplies at most
40 recent exchanges, 16 older hinted references and six previous scope references.
Native-session recovery uses that bounded supplement rather than replaying the entire
conversation. The assistant can request one missing clarification instead of starting
the roles. Only a later explicit launch starts work after that clarification.

`deep_analysis_context.py` validates selected message IDs against the conversation and
launch cutoff, pairs selected acknowledgements with their preceding exchange, and
rejects unavailable or stale references. It preserves the exact human-submitted need.
Git and document manifests are frozen at launch, before context preparation. The
resulting `cycle_scope` records retained exchanges, their contextual classifications,
prior analysis references, and the preparation job ID. All conversation excerpts are
marked as non-evidence. Other cycles' conclusions are not injected as verified facts.
The independent roles still consult authorized sources; custom instructions cannot
grant additional access. Row locks, revisions and cancellation checks prevent concurrent
launches or late context responses from creating overlapping cycles. No new tables or
migration are required. Legacy explicit message-ID API payloads remain accepted.

Each cycle retains its own frozen dossier and subsequent answers/decisions. Old results remain accessible
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
by default **four per account and two overall**. Discussion and deep-analysis calls
use the same budgets. Account aliases share reservations for the detected account.
One conversation permits only one active operation at a time.
AI invocations use a one-hour execution limit by default, including conversational
turns, library drafting and deep-analysis checkpoints. Runtime validation and the
Antigravity CLI accept the same bounded limit. Database/network tool limits remain
separate. An explicit retry applies the current invocation budget and records the
change without replacing frozen evidence, role sessions or completed checkpoints.
An execution timeout is reported explicitly; it never becomes successful verification.
The process supervisor follows the invocation's configured budget, with a sixty-second
margin for transport and checkpoint persistence. Stale conversational/library jobs are
not recovered before that budget and a further fifteen-second recovery margin expire.
Persisted installation settings retain their selected budget; the schema default does
not silently replace a previously saved value.

The roles inside an analysis remain sequential while other conversations run alongside
it. Actual provider throttling, quota, authentication and backoff still constrain work.
A waiting job does not reserve all future roles. Native sessions and checkpoints remain
associated with their own request and attempt.

Cancellation identifies the exact runtime attempt. A reservation is retained until
that attempt is known to have stopped; stale completion cannot release another job's
slot. Interrupted jobs recover from recorded state. Configuration changes and CLI
maintenance coordinate with all active invocations, including pending stops.

The reference agent container shares two CPUs, 2 GiB memory and 256 task slots.
Its execution admission is additionally capped at two invocations. Excess work
returns BUSY to the existing scheduler. The shared sandbox UID is limited to 128
tasks in both `runtime/relay.py` and `runtime/restrict.py`; Linux includes threads
across invocations and PID namespaces in that UID budget. Runtime locks are released
after execution, active controls remain until cleanup, and a still-running process
is killed/reaped on an unexpected execution failure. Persisted native session state
does not require keeping a CLI process resident between turns.

Raising scheduler limits does not raise that runtime cap or add provider/host capacity. The HTTP
request limiter is a different mechanism. SQLite development tests do not prove
PostgreSQL locking or multi-process concurrency; use disposable PostgreSQL tests.

## Local retirement and artifact ownership

`core/local_deletion.py` handles cycle deletion and local publication removal.
Migration `0054_local_analysis_publication_retirement` adds nullable retirement
timestamps, visibility managers and no destructive table changes.

- `DELETE /analyses/{analysis_id}/runs/{number}` requires explicit confirmation.
  Job, conversation and cycle locks follow completion's lock order. Active current
  executions are fenced and cancelled; runtime acknowledgement must precede final
  cleanup. Worker maintenance retries pending stops even after the browser closes.
  The authenticated `/sessions/release` gateway retires only validated exclusive
  role contexts, after runtime work and file handles have finished. Shared discussion
  sessions and contexts used by other jobs remain.
- Analysis runs and result versions disappear through their default visibility
  managers. Their identifiers and sequence numbers remain reserved, and new number
  allocation uses the unfiltered managers. Unreferenced result contents, artifacts
  and owned materialized contexts are removed; frozen evidence referenced by tickets,
  transferred documents or derived questions remains accessible to those dependents.
  Shared Git caches and conversation workspaces are preserved.
- `DELETE /tickets/{ticket_id}` requires explicit confirmation and a confirmed
  publication with no attachment transfer in flight. It hides only that publication
  and its conversation event, clearing duplicated payloads while retaining external
  identity, destination and idempotency data. The default publication manager remains
  unfiltered so removed records still prevent duplicate creation. No provider delete
  or update API is called, and sibling publications remain intact.

These operations are not secure erasure. See [retention](../SECURITY.md#retention-and-backups)
and [local administration](local-administration.md) for installation-wide cleanup,
ownership checks and reproducible resource measurements.

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
When an idle conversation starts a new investigation with a different frozen SHA, its
clean working copy is recreated at that SHA under the repository lock. Prior result
baselines and retained mirror objects remain unchanged; historical source disclosure
reads those immutable objects and does not recreate an active workspace.
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
