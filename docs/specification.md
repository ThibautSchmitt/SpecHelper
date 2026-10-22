# SpecHelper functional scope

SpecHelper turns a business need into a concise ticket and detailed `goal.md` using actual project sources. It prepares implementation without modifying sources or business data and without automatically creating a ticket or pull request.

## Team instance

One installation serves a trusted team. Requests and connections are shared; there are no application accounts, per-user permissions or private spaces. Infrastructure controls remote access.

## Settings

- Named GitHub/GitLab source connections, including forks and self-hosted GitLab.
- Guided GitHub, ChatGPT and Claude authentication; read-only GitLab tokens when needed.
- Multiple AI configurations with model, shared identity, default and availability preference.
- Named environments with multiple Git repositories/branches and optional PostgreSQL.
- Environment creation, editing, synchronization and confirmed deletion.
- Instance name, short label, color, application language and permission to compare new requests.
- Administrative role instructions, inherited skills and bounded verification policy.

**Application language** under **Settings → Instance** selects English or French for the interface and newly created analyses. French is the default, preserving existing installations. A request's language is frozen at creation and used for clarification, later discussion and generated artifacts. Switching the instance language does not translate or overwrite historical artifacts.

The PostgreSQL test checks connectivity, a read and read-only permissions. It returns three simple statuses without database inventory or diagnostics.

## Business workflow

Users select an environment, describe their need and attach files. Understanding may ask questions before full exploration. Answers resume the same request. Source SHAs and the database connection are frozen in a baseline; the database baseline is not a data snapshot.

Without comparison, an available analyst is selected automatically. Comparison runs
one analyst and one independent counter-analyst, followed by comparison and an
optional verifier. Consecutive roles prefer distinct actual model families; an
eligible third family is preferred for verification. Same-family fallback requires
administrative permission and a warning. Otherwise the request waits explicitly.
Public roles use separate terminal contexts and writable directories. Only structured
conclusions and evidence cross role boundaries; one targeted check is allowed.
See [role configuration and verification](orchestration.md).

## Results and discussion

The ticket includes a title, brief context, need, expected behavior, solution, impacts, risks and acceptance criteria. The goal details business intent, existing behavior, required behavior, technical context, repositories/SHAs, files and symbols, constraints, implementation guidance, criteria, tests and useful attachments. It requires independent source verification before modification.

Both artifacts can be copied and downloaded. Discussion after a result creates a new immutable version; previous versions remain available. `PARTIAL` indicates material uncertainty, distinct from technical failure.

## Dashboard and ticket publication

Requests, Tickets and Settings share a persistent instance sidebar and live task
queue. Desktop displays three columns; smaller screens retain navigation and a
queue drawer. Connection indicators reflect observed status. Queue cards expose
FIFO order, actual elapsed time, clarification, completion and failures without
inventing quota information or completion estimates.

GitHub Issues, GitLab Issues, Jira and GLPI connectors operate independently of
analysis agents. Settings stores encrypted credentials and allowed destinations.
A completed result opens a publication dialog with target templates, required
fields, editable content and preview. Only explicit human confirmation creates an
external ticket. Metadata revisions, persistent operation identifiers and
uncertain-write reconciliation guard against stale forms and duplicate creation.

Tickets lists confirmed publications, with search and platform/environment filters,
external links and the exact immutable source version. See
[publication behavior and supported APIs](ticketing.md) and the
[v1.3 acceptance report](acceptance-v1.3.md). Named Git sources, assistant models,
account quota grouping and execution attribution are described in
[connections and availability](connections.md).

## Execution and security

The queue is persistent and the default worker runs requests sequentially. Different browsers can submit different requests. Concurrent operations on the same request are guarded.

Git mirrors are shared; analysis worktrees are isolated and immutable. The Linux runtime mounts sources, cache and files read-only and does not expose credentials to agents. Temporary PostgreSQL access is filtered and read-only. Instructions in sources or attachments are untrusted data.

Orchestration is bounded to 285 seconds, with a 295-second supervisor limit per job, excluding queue/capacity waits. Latency targets depend on the provider. Quotas and reset times not officially exposed remain unknown.

Out of scope: multi-tenant management, request-history search, automatic PRs, business writes, proprietary graphs and advanced scheduling.

## Project questions

Questions explain existing behavior through the same analysis and shared queue as
requests. They support attachments, configured independent comparison, clarification during
exploration and versioned follow-ups. Answers identify verified facts, inferences,
uncertainties and Git references. No ticket, goal or external publication is created.

Users can copy the displayed answer, create optional business/technical/mixed
Markdown documentation tied to that version, or open the normal request form with
a reviewed, removable Markdown context attachment. The user explicitly describes
the desired change. Derived requests have independent sessions and results, keep
source-question provenance and recheck current sources before trusting transferred
conclusions. Later question versions never rewrite transferred attachments.
See [questions](questions.md) for the complete workflow.

## Appearance and analysis preferences

Requests and questions choose their analysis policy automatically from instance
settings and authenticated assistant roles. Their forms collect an environment,
a business category, text and optional attachments; no comparison checkbox is
shown. Configuration, role instructions and skills remain in Settings. Existing
requests retain their recorded comparison policy and immutable artifacts.

The shared shell uses fixed navigation, central content and a desktop task panel.
The task panel groups running, waiting, clarification, completed and failed work;
measured position changes respect reduced motion. Cards distinguish the current
assistant from previous execution records and identify non-AI connector work.

Light, dark and system preferences persist in the browser. System mode follows
live device appearance changes. Theme changes preserve the same controls and
page hierarchy. Settings retains shared instance color and language controls.
