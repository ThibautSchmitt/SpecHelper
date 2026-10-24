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
- Instance name, short label, color, application language and global instructions.
- Connection-specific instructions, allowed system roles and global skills loaded on demand.

**Application language** under **Settings → General** selects English or French for the interface and newly created analyses. French is the default, preserving existing installations. A request's language is frozen at creation and used for clarification, later discussion and generated artifacts. Switching the instance language does not translate or overwrite historical artifacts.

The PostgreSQL test checks connectivity, a read and read-only permissions. It returns three simple statuses without database inventory or diagnostics.

## Business workflow

Users select an environment, describe their need and attach files. Understanding may ask questions before full exploration. Answers resume the same request. Source SHAs and the database connection are frozen in a baseline; the database baseline is not a data snapshot.
No request or question category is required at entry. Files use a compact keyboard-accessible
control with drag-and-drop, size/removal feedback and validation errors.

Every current analysis uses Analyst, independent Counter-analyst and Verifier.
Independent omission discovery, coverage review and scoped evidence remain mandatory.
Consecutive roles prefer distinct actual model families, with an eligible third
family preferred for verification. One family may perform separate roles in fresh
contexts with an explicit diversity limitation. A forbidden role is never substituted.
Global and connection instructions remain below the fixed role/security mission;
environment resources provide factual context. Active compatible global skills are
discoverable by all assistants and loaded only when useful.
See [step scheduling and independent coverage](orchestration-v2.4.md).

## Results and discussion

The ticket includes a title, brief context, need, expected behavior, solution, impacts, risks and acceptance criteria. The goal details business intent, existing behavior, required behavior, technical context, repositories/SHAs, files and symbols, constraints, implementation guidance, criteria, tests and useful attachments. It requires independent source verification before modification.

Both artifacts can be copied and downloaded. Discussion after a result creates a new immutable version; previous versions remain available. `PARTIAL` indicates material uncertainty, distinct from technical failure.

## Dashboard and ticket publication

Requests, Questions, Tickets and Settings share a persistent instance sidebar and live task
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
Persistent presentation drafts retain the selected real template/type or short standard
format and optional business/technical detail. Changing these does not re-run analysis
or alter `goal.md`. Files require explicit opt-in and individual selection; partial
results cannot bypass missing independent checks through export or publication.

Tickets lists confirmed publications, with search and platform/environment filters,
external links and the exact immutable source version. See
[publication behavior and supported APIs](ticketing.md) and the
[v1.3 acceptance report](acceptance-v1.3.md). Named Git sources, assistant models,
account quota grouping and execution attribution are described in
[connections and availability](connections.md).

## Execution and security

The persistent shared queue schedules ready steps across available compatible connections. Distinct requests may advance concurrently; only one checkpoint of a request may execute at a time. Atomic attempts and account/quota leases guard against duplicate work, including with multiple workers.

Git mirrors are shared; analysis worktrees are isolated and immutable. The Linux runtime mounts sources, cache and files read-only and does not expose credentials to agents. Temporary PostgreSQL access is filtered and read-only. Instructions in sources or attachments are untrusted data.

There is no fixed total business-analysis deadline. Technical SQL/tool timeouts, resource caps, heartbeat recovery and loop guards remain explicit. Clarification releases capacity and resumes the same job with unaffected checkpoints. Cancellation stops the exact runtime attempt and its process tree before releasing capacity. Quotas not officially observed remain unknown.

Out of scope: multi-tenant management, request-history search, automatic PRs, business writes, proprietary graphs and advanced scheduling.

## Project questions

Questions explain existing behavior through the same analysis and shared queue as
requests. They support attachments, mandatory independent review, clarification during
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
mandatory system roles and available compatible assistants. Their forms collect an environment,
free text and optional attachments; no category or comparison checkbox is
shown. Global instructions, connection instructions and the global skill library remain in Settings. Existing
requests retain their recorded comparison policy and immutable artifacts.

The shared shell uses fixed navigation, central content and a desktop task panel.
The task panel groups running, waiting, clarification, completed and failed work;
measured position changes respect reduced motion. Cards distinguish the current
assistant from previous execution records and identify non-AI connector work.

Light, dark and system preferences persist in the browser. System mode follows
live device appearance changes. Theme changes preserve the same controls and
page hierarchy. Settings retains shared instance color and language controls.

### Consolidated settings

Main navigation contains Requests, Questions and Tickets; the bottom-left Settings
button opens General, AI & Agents and Environments. Each setting has one editing
location. General saves browser appearance separately from shared identity,
language and color. General contains global instructions. AI & Agents contains connection instructions, role eligibility, model selection and the global skill library.
Environment-specific ticket connectors are checked server-side during publication.
See [settings](settings.md) for provider quota visibility and migration guarantees.

## External official references

Global instructions request official external documentation only for relevant rules,
contracts, standards or external versions. Environment URLs/notes are non-exclusive
factual hints, frozen with the context. Public HTTPS reading is scoped and bounded;
actual fetched-page receipts preserve URL, title, consultation date and hashes.
Claims record applicability, effect/version, jurisdiction and scope; unverified or
undated regulatory applicability remains a limit. Web evidence cannot establish
deployment behavior without Git/SQL observations. See [official references](official-references.md).
