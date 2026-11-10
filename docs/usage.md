# Using SpecHelper

The main navigation contains **Home**, **Analyses** and **Tickets**.
**Administration**, at the bottom left, opens configuration. Your conversation is
with SpecHelper or the name configured for the instance, not separate provider speakers.

## Start a discussion

1. Open **Analyses → New analysis** and select an up-to-date environment.
2. Describe what you want to understand or change. Attach only necessary, authorized files.
3. Start the discussion and add questions, corrections or useful examples.

The first phase uses one assistant. It can inspect permitted sources and ask useful
factual questions. It does not automatically launch independent reviews after each
message, and its responses are exploratory rather than verified conclusions.

The assistant keeps its selected provider, model and native session where supported.
Reloading or reopening in another authorized browser preserves the application history. If
native resumption becomes impossible, the application reports a new session and
reconstructs bounded context from saved messages instead of claiming unchanged continuity.
A change to the selected connection's model, reasoning or identity automatically starts
a new session on the next requested turn, using the saved conversation history. The
new session is shared across authorized browsers and recorded in the conversation;
existing sessions and answers remain intact. No response is generated just by opening
the page, and selecting a different connection remains an explicit choice.

If a turn fails, use **Retry** after checking the reported cause. This explicitly
starts a new native session with saved, bounded context; it does not change the selected
connection on its own. With an empty composer, your pending message is reused rather
than appended again. Explicit configuration changes remain visible in the AI history.
Antigravity must finalize the current turn before its structured response is accepted.
An old cached response without a new completion is shown as a failure, not as the
answer to your new question. Confirmed invalid replies are excluded from recovery
context while their original records are retained for traceability.

Below the analysis title, the discussion shows its selected AI connection, model and
reasoning setting. These are recorded session values, not replacements taken from
subsequent settings edits. When the provider reports an actual model for a default
selection, that observed model can be displayed.
An **AI history** line retains previous connections with their recorded model and
reasoning settings. The current connection is identified separately; repeated native
session restarts with the same configuration do not add duplicate entries.

If its quota is exhausted, or its connection is removed, disabled, disconnected or
no longer authorized for the Analyst role, **Choose another AI** opens a list of currently
available Analyst connections. Choose a connection and inspect its model and reasoning
before selecting **Continue**. Leaving the selection or choosing **Cancel** keeps the
original connection and pending request. SpecHelper never transfers it automatically.
Availability and the selected configuration are checked again on confirmation.
If a message cannot be sent because its assistant is no longer authorized or available,
the same action appears directly beside the error, above the message composer.
Choosing another assistant preserves the unsent message and attached files.

A confirmed change starts a new native session, even for another ChatGPT account.
The recorded history and frozen project context are provided for recovery; private
native session state is not migrated. Previous AI replies remain unverified hypotheses
and may need reinvestigation. The conversation records the change. A pending message
is retried once without being appended again; a finished discussion waits for the next
user message. An active execution must finish or stop before a transfer is possible.

Analyses, messages and the Activity panel are shared across authorized browsers.
The same conversation resumes its own AI session when another team member continues it.
A conversation accepts one active operation at a time; refresh before sending if another
browser has already changed it. There are no private user spaces or organization tenants;
see [SECURITY](../SECURITY.md).

## Find and organize conversations

**Analyses** lists durable conversations by last activity. Search titles, message
contents or result descriptions; filter by environment and one of four states:

- **In discussion**: no active operation or pending clarification.
- **In progress**: a message or deep analysis has been accepted and is being processed.
- **Waiting for AI**: an operation has a recorded availability/capacity wait.
- **Reply expected**: a clarification requires an answer.

An incident indicator remains visible after an error, cancellation or interruption.
Open the conversation to inspect the cause, retry safely or continue discussing.
A completed or partial analysis is an operation outcome, not a closed conversation.

Rename a conversation from its title. **Archive** removes it from the active list
without deleting messages, native sessions, analyses, reports or tickets. Select
**Archived conversations** to find it and **Unarchive** to resume. Archiving does
not cancel an active operation or automatically delete anything. Confirmed deletion
hides the conversation while preserving retained publication provenance.

## Follow the work

The conversation, message composer and analysis/ticket actions share one card.
An accepted turn shows an immediate acknowledgment, followed by a single progress
element. Consecutive identical finished operations are grouped with a count; failures
remain separate from successes. When detailed events exist, expand it to inspect source
searches, file reads, Git history or command execution. Without a recognizable action,
only the operation's real state is shown. No empty disclosure is shown for a discussion
without tool events.
No detailed action is invented when the provider sends no usable event; a
quiet active invocation remains a neutral processing state with observed elapsed time.

During deep analysis, the same element exposes the three roles and their real states.
Role names use the same colored tags as **AI connections**; their execution states
remain separate labels beside the tags.
Future roles have no invented work steps. A green check records a completed operation,
not proof that every conclusion is correct. Waiting for capacity, quota exhaustion,
clarification, interruption and technical failure remain distinct.
Completed, interrupted and cancelled analyses stay at their place in the conversation;
later discussion messages do not move their progress elements.

Response text appears progressively when the provider exposes an eligible user-facing
field. A draft is labelled pending validation. Codex can deliver message text only at
completion, Claude can expose selected structured-output deltas, and Antigravity may
expose it only in its terminal result. Token-by-token output is not guaranteed.
Private reasoning, raw commands and tool output are not conversation messages.

The view follows new text while you are at the bottom and lets you read older messages
without pulling you back down. Recorded observations survive reloads. A lost tracking
connection is shown explicitly; it is not treated as proof that the model failed.
The conversation header shows the request date and last message date; individual
messages do not repeat dates or assistant/user identity headers.

**Activity** is closed by default and remembers its state. Its badge counts clarifications
and actionable errors, not running analyses. The drawer layout adapts to smaller screens.
Open a listed analysis to respond, inspect a problem, cancel active work or use an
available safe retry. A waiting analysis does not reserve all future roles.

## Launch deep analysis

Choose **Deep analysis** when the subject is ready for independent checks. A centered
modal contains one editable **Need to analyze** field. Review its suggested wording,
or enter the need if the current subject is ambiguous, then choose **Launch deep analysis**.
There is no manual message selection. Opening the modal does not call an AI or start work.

After confirmation, the conversational session selects relevant exchanges from its
available context and a bounded supplement of saved messages. Short confirmations
such as “yes” stay with the exchange they answer; they are never standalone needs.
The exact submitted need remains authoritative. If essential context is missing,
SpecHelper asks a short question in the conversation without starting the three roles.
Answer it, then explicitly launch the analysis when the need is clear.

You can run several cycles in the same conversation. Each keeps its own subject,
role sessions, frozen Git references, evidence and results. New cycles do not replace
previous results or close the conversation. One conversation per topic is often easier
to follow, but is not required.
The application freezes the submitted need, retained exchanges, attachments,
environment documents and Git references for that cycle. Documents remain available
for targeted consultation rather than all being read at launch. User declarations,
clarifications and assistant hypotheses are labelled as context, not technical proof.
Relevant earlier analyses are references to recheck, not facts to inherit blindly.
Source claims still require the roles' own authorized verification.

The roles execute sequentially inside the analysis:

1. **Analyst** investigates the need and authorized sources.
2. **Counter-analyst** performs an independent initial investigation, then confronts
   findings and searches for omissions, contradictions and counterexamples.
3. **Validator** checks evidence and unresolved issues before a result is accepted.

The role sessions are separate from each other and from the discussion. Other
conversations may execute concurrently within [deployment limits](installation.md#concurrent-work).
A same-family fallback, when allowed, retains independent sessions but reduces family diversity.

Any role can request a clarification in the same conversation. Answer the question
or correct the scope. Previously supplied answers are reused rather than intentionally
asked again. A factual response is not automatically a normative business decision;
only an explicitly confirmed business choice enters that decision history.
Technical source/database access failures remain technical problems, not business questions.

Cancellation preserves messages and completed observations. Retrying an interrupted
step reuses accepted checkpoints where applicable and must wait for the old runtime
attempt to stop. It does not skip mandatory checks to obtain a result.

## Read the result and its limits

The final message is a concise synthesis. Important uncertainties remain visible.
A partial result means execution ended with incomplete or blocking verification; it
must not be read as a fully verified answer even when every role has finished.

Open **Analysis report** for detailed business/technical sections, evidence, frozen
Git references, decisions and provenance. Optional individual role reports can be
downloaded as Markdown; they are not automatically included in tickets.
Each result also offers **View business report** and **View technical report** beside
**Prepare a ticket**. These retained analysis results open in the same
safe Markdown reader and can be downloaded separately. Each belongs to that exact
cycle/version, including when later conversation topics have changed. Business
reports emphasize functional conclusions; technical reports include retained source
excerpts and executed SQL. Reports read saved evidence without new AI calls or
business queries. Formal ticket documents are generated separately at publication.
An interrupted cycle with recorded findings can expose partial
reports; its findings remain explicitly without complete independent verification.
Reviewed explanatory diagrams may be expanded where useful. Unchecked relationships
are omitted rather than presented as established behavior.

Source evidence establishes only its actual scope. Code inspection is not a live UI
session; a database query is a bounded observation, not a universal proof; document-read
telemetry is not comprehension. External references need actual consultation, dates
and applicability. No reliability percentage is inferred from model diversity.

Continue discussing after a result without rerunning all three roles. New messages
do not rewrite or retroactively verify that earlier result. Launch another deep cycle
when the changed need or new evidence requires verification. A linked evolution keeps
the source result and its original scope.

## Inspect sources

In a response, **Sources and checks** expands the recorded evidence without
rerunning an agent or a database query. Short **SQL check** references open the
corresponding executed SQL, row count and result-limit notice.
Standalone source-reference paragraphs are grouped in this same collapsed
disclosure instead of repeating file lists in the answer. Subsequent explanatory
sentences and verification limits remain in the response. Inline code references
within an explanation and literal code examples are preserved. Explicit role
mentions use the same role colors and badges as **AI & Agents → Connections**.
Rejected or unavailable SQL attempts stay in diagnostics rather than the source
disclosure. Consultation dates and internal technical receipt IDs are not shown there.
Code references use the frozen Git blob and cited lines, never the latest branch
or an active agent's worktree. Web references show retained page text or an exact
recorded quotation. Documents show the retained version, a text preview when
available and a source download. A preview is distinguished from an exact cited
passage; missing excerpts remain explicitly unavailable. Source content is treated
as untrusted information, never executed. SQL and code excerpts have local syntax
highlighting. Documents and web excerpts open in a Markdown reading view with
headings, lists and tables; **Source text** shows the exact retained text. Switching
views does not refetch a source, rerun a query or invoke an AI. Raw HTML is not
rendered and remote Markdown images are not loaded. Tables have shared cell spacing, borders and their own
horizontal scrolling when needed on a small screen.

Generated documentation reuses these recorded sources from the selected answer
version. Business documentation keeps functional conclusions, essential limits,
document links and recorded web quotations; it does not append raw SQL or source
code. Technical documentation includes frozen code excerpts, executed queries and
retained document/page excerpts. Mixed documentation includes both presentations
without repeating the source annex. Rejected or unavailable SQL attempts are not
exported as evidence. A source citation alone never upgrades a finding's verification
status. Exports do not rerun investigations or queries, and saved documents keep
their generated content when the conversation or environment later changes.

## Prepare and publish a ticket

Choose **Prepare a ticket** in a conversation. SpecHelper asks the conversational
assistant to write a title and description, then presents the draft in a centered
**Create ticket** modal. Content, publication destination and optional documents
share this one window. The genuine queued/running operation appears as **Preparing the ticket…**.
This is one drafting turn in the existing native session, not an independent deep
analysis. If essential information is missing, the assistant asks a short question
instead of inventing a requested change.

Each conversation has at most **one active unpublished draft**. Its discreet **Draft**
action reopens it without regeneration. Saved corrections remain intact. If you want
a ticket for another need while a draft exists, choose **Resume draft**, **Replace
draft** or **Cancel**. Replacement requires explicit confirmation of the current
draft and revision. Its content remains intact if generation fails. The interface
does not list historical subjects or put draft cards into the message timeline.

The native session supplies continuity for returning to an earlier need. Recent
exchanges, authorized reference documents and relevant analysis results can inform
the writing; the last message alone does not define the subject. When a native
session is lost, the existing reconstruction mechanism uses saved history. Missing
essential context must be requested rather than fabricated.

The description opens in **Preview**, with formatted headings, lists, tables and code.
Choose **Edit** to change the Markdown, then **Preview** to check it. Switching views
preserves unsaved corrections and makes no AI or save request. Edit **Title** and
**Description**, then **Save** or **Publish**. Closing saves current edits and selected
destination options; a failed save keeps the window open and the inputs intact.
**Copy draft** copies the title and Markdown description. **Improve with AI**, beside
the description, uses the current draft as its editing base and can
integrate relevant later clarifications, new documents and late analysis results.
Unrelated intervening subjects must not change the ticket's scope. The proposed
update is shown for review: choose **Apply** or **Keep my draft**. The saved document
is not overwritten before this choice. A failed or unnecessary update keeps it
unchanged; a concurrent manual save invalidates a delayed proposal.

Deep analysis remains optional for preparing, updating and publishing. A relevant
analysis can supply existing conclusions and evidence, but new requirements are not
independently verified merely because a prior cycle completed. The modal shows a
short verification indication under the collapsed **Additional options**. Launching an
independent analysis remains a separate, explicit action there. It saves current edits, opens an editable
need prefilled from the ticket and starts only after confirmation. The draft remains
available during analysis. After it completes, use **Improve with AI** on the same draft.

**Documents to attach** offers `goal.md` (selected by default), a business report and
a technical report (unselected by default). All three can be deselected. Saving or
updating the ticket generates none of these files. After choosing the destination
and pressing **Publish**, SpecHelper generates only missing or outdated selected
documents in one writing turn, then asks for final confirmation before any external
creation or transfer. Unchanged documents are reused individually.
The final saved title, description and destination fields, relevant exchanges,
reference documents and associated analysis results provide their context. No new
independent investigation or business query is launched. Missing facts, hypotheses,
potential impacts, investigations and open decisions stay explicitly identified.
The files must be ready and match the ticket and its sources before external creation
begins. On failure, retry or deselect affected files before confirming again. Closing
the preparation stops the browser's publication sequence; a running writing job can
finish and be reused later. Analysis evidence remains available independently of tickets.
Generation uses the authorized conversation assistant and preserves its role checks.
If it cannot be used, choose another authorized analyst explicitly when retrying.
That writer receives the saved ticket and bounded context in a separate writing
session; the conversation's selected AI, native session and roles stay unchanged.

Account and destination selection are directly available in the same modal. Choose an
enabled, verified connection associated with the environment and an accessible
destination. Multiple accounts remain separate choices. A failure never switches
accounts silently. Required provider fields stay visible. **Additional options**
contains optional fields, project templates, labels and searchable compact assignee
selection when supported. Original attachments remain an explicit choice there.
The title and description already show the content to send: there is no duplicate
publication preview or second preparation step. Changing destination preserves the
conversation draft while loading that destination's saved fields. Internal
reconciliation markers stay out of the reading view; the provider payload and
stored publication reference retain duplicate protection.

Publication always requires human confirmation. If independent verification is
missing or the sent content is not covered by it, choose **Publish anyway** to
acknowledge that limit. No agent publishes or launches the three roles automatically.
A failed write retains the draft. An uncertain write must be verified with its
original publication reference; it is never resent blindly.

Confirmed creation frees the active draft and leaves **Ticket published** permanently
in the conversation, with the platform, reference and **Open published ticket** link.
Each successive publication has its own event, retained after reload or archive.
Retries do not duplicate events, and failures never produce success links. The
**Tickets** page contains only confirmed external publications. Historical document
and publication records remain retained for traceability; they do not form a second
draft-management interface.

Destination-specific behavior matters:

- GitHub supports repository Markdown templates and YAML issue forms; GitLab uses
  exposed project issue templates. Inherited templates depend on the target service.
- Jira uses issue types and creation metadata, including supported required fields;
  its description uses ADF text paragraphs.
- GLPI uses accessible legacy template/entity/category metadata and escaped HTML.
  Unsupported mandatory rules require its native form; server validation is authoritative.
- Missing mandatory information is left for human completion, never invented.

### Optional files

**Include attachments** starts unchecked for original uploaded files. Selected ticket
documents use the separate **Documents to attach** choices and do not require an
analysis. A destination's upload capability is checked before generation and sending;
unsupported destinations require deselecting documents, rather than promising an upload.
The original-file picker accepts XLSX workbooks and UTF-8 SQL documents in addition
to the supported PDFs, DOCX, images and text formats. SQL is read, never executed;
workbook macros and external-data containers are rejected. Legacy DOC/XLS is unsupported.
Accepted by SpecHelper does not mean accepted by the destination: GLPI's native
uploadable document-type catalogue determines which extensions can be transferred.
Unsupported files remain in the conversation but cannot be selected for that
destination. A GLPI instance that disallows Markdown also cannot receive generated
`goal.md` or reports; deselect these before publication or have its administrator
review its native document policy. SpecHelper never changes that policy automatically.
A detailed diagram annex is separately selectable
for supported standard-format publications. Up to 20 selected files and 50 MB total
are accepted; each original file must also meet the 25 MB safety limit. Preview hashes,
sizes and types are rechecked before transfer.

GitLab, Jira and legacy GLPI have upload adapters. The supported GitHub Issues API
has no equivalent upload operation here, so file transfer is unavailable there.
Reports and individual role downloads remain optional; they are not implicitly attached.

Issue creation and file delivery have separate outcomes. A successful issue remains
recorded if an attachment fails. An uncertain write is never retried blindly.
Check the per-file delivery result as well as the ticket's publication status. For GLPI,
the document must have a stored filename/path and, when returned, a matching checksum
before SpecHelper links it to the ticket and confirms delivery. Use
**Verify existing publication** and inspect the target when necessary: delayed search
or insufficient permissions can prevent immediate reconciliation. An unstarted file
transfer may resume against an existing issue without creating another issue.

## Find published tickets

**Home** summarizes mutually exclusive work needing action, work in progress and
available results. **Analyses** provides search, filters and the conversation history.
**Tickets** is a compact history of confirmed external publications. Each row represents
one external ticket, including when one conversation or prepared document has several
publications. Rows show the title, platform, external reference, environment, publication
date and optional connection name. **Open** goes directly to the saved external ticket
in a new tab. An optional secondary link returns to the source conversation, including
archived conversations.

Only confirmed publications with an external identifier or reference appear. Drafts,
active operations, failures and uncertain publications stay in their conversation and
existing operation details; they are not promoted to published tickets. Historical
confirmed references with missing or unsafe URLs remain visible with **External link
unavailable**. SpecHelper does not guess links or fetch external ticket content.

Search published titles, references, platforms or projects. **Filters** exposes platform
and environment; there is no status filter or selected-ticket preview. Pagination appears
only for multiple pages. **Refresh** reloads local publication records, without synchronizing
external workflow states. Preparing a ticket never launches a deep analysis automatically,
and uncertain publications still require safe verification of the original operation.

To hide one confirmed publication, use its **… → Remove from SpecHelper** action and
confirm. It disappears from this list and its publication element in the conversation;
the external ticket is neither deleted nor changed. Other publications, including
those from the same draft or conversation, remain. Wait for any attachment transfer
to finish before removing its publication. Failures and uncertain operations must be
resolved through their existing conversation actions instead.

Minimal publication identity and duplicate-prevention references remain locally.
Removing an entry does not authorize SpecHelper to repeat that external creation.

## Delete a deep analysis or conversation

Use **… → Delete deep analysis** on the relevant progress element and confirm
**Delete this analysis and its results? This action cannot be undone.** This removes
that cycle and its results from the conversation. The conversation, its independent
messages, other analyses, drafts and published tickets remain.

For an active current-format analysis, SpecHelper requests cancellation and waits for
the exact runtime attempt and its exclusive role sessions to stop before completing
cleanup. The worker continues pending cleanup if you close the window. Older analysis
formats can require stopping the operation first. Do not treat a pending stop as
completed deletion. Shared conversation sessions and evidence required by retained
tickets or other dependent records are preserved.

The separate **Delete conversation** action concerns the whole conversation, not one
cycle. It requires its own confirmation and retains necessary publication provenance.
Renaming or archiving remains available when you want to keep the history. Local
deletion and retirement are not secure erasure; see [retention](../SECURITY.md#retention-and-backups)
and [local administration](local-administration.md#retiring-an-analysis-or-publication).
