# Architecture

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
session or silently switch providers. Session directories and ownership are scoped
to the conversation and environment; there is no shared cross-conversation memory.

**Launch deep analysis** captures a versioned need and resource baseline. Human
statements and confirmed decisions are distinguished from exploratory AI hypotheses.
The discussion's native session is never reused as an Analyst or Counter-analyst session.

Within one deep cycle, the roles execute sequentially:

1. The Analyst investigates authorized evidence.
2. The Counter-analyst starts independently of the Analyst's conclusions, then confronts them.
3. The Verifier checks the findings, evidence and unresolved material issues.

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

Ticket publication is a separate backend operation. Agents cannot write business data
or publish tickets through their resource tools. Destination credentials, preview edits,
templates, attachments and uncertain-write reconciliation have their own validation.

## Trust boundaries and implementation pointers

New conversations use browser-cookie ownership; legacy shared records remain shared.
This is not individual-account authentication or tenant administration. Access settings,
AI connections and deployment administrators remain trusted. The runtime supervisor
needs namespace privileges; its analysis children run as a separate non-root identity
with restricted mounts, network access and capabilities. See [SECURITY](../SECURITY.md)
for the complete boundaries and residual risks.

| Area | Source |
| --- | --- |
| API and data | [backend/core](../backend/core) |
| Discussion ownership | [discussion_access.py](../backend/core/discussion_access.py) |
| Persistent discussion | [discussion.py](../backend/core/discussion.py) |
| Queue supervision | [management commands](../backend/core/management/commands) |
| CLI adapters and sandbox | [runtime](../runtime) |
| Conversation and progress UI | [frontend/src](../frontend/src) |
| Publication adapters | [ticket_providers.py](../backend/core/ticket_providers.py) |

The optional indexing experiment is evaluation tooling, not the production navigation
path. Recorded quality limits are in [Qualification evidence](evidence/qualification.md).
