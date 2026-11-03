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
A configuration change requires explicit session recovery; no silent account switch occurs.

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

If its quota is exhausted, **Continue the analysis with…** opens a list of currently
available Analyst connections. Choose a connection and inspect its model and reasoning
before selecting **Continue**. Leaving the selection or choosing **Cancel** keeps the
original connection and pending request. SpecHelper never transfers it automatically.
Availability and the selected configuration are checked again on confirmation.

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
Rejected or unavailable SQL attempts stay in diagnostics rather than the source
disclosure. Consultation dates and internal technical receipt IDs are not shown there.
Code references use the frozen Git blob and cited lines, never the latest branch
or an active agent's worktree. Web references show retained page text or an exact
recorded quotation. Documents show the retained version, a text preview when
available and a source download. A preview is distinguished from an exact cited
passage; missing excerpts remain explicitly unavailable. Source content is treated
as text, never executed. Tables have shared cell spacing, borders and their own
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
modal. The genuine queued/running operation appears as **Preparing the ticket…**.
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

Edit **Title** and **Description**, then **Save** or **Publish**. Closing warns about
unsaved edits. **Update with AI** uses the current draft as its editing base and can
integrate relevant later clarifications, new documents and late analysis results.
Unrelated intervening subjects must not change the ticket's scope. The proposed
update is shown for review: choose **Apply** or **Keep my draft**. The saved document
is not overwritten before this choice. A failed or unnecessary update keeps it
unchanged; a concurrent manual save invalidates a delayed proposal.

Deep analysis remains optional for preparing, updating and publishing. A relevant
analysis can supply existing conclusions and evidence, but new requirements are not
independently verified merely because a prior cycle completed. The modal shows a
short verification indication. Launching an independent analysis remains a separate,
explicit action. After it completes, use **Update with AI** on the same draft.

**Publish** opens account and destination selection in the same modal. Choose an
enabled, verified connection associated with the environment and an accessible
destination. Multiple accounts remain separate choices. A failure never switches
accounts silently. Complete required provider fields and review the exact content.
A new destination preview starts with the saved draft; an existing destination draft
keeps its own edits until **Use prepared draft** explicitly replaces them.

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

**Include attachments** starts unchecked. Select originals and `goal.md` individually
when the destination supports uploads. `goal.md`, analysis reports and diagram annexes
require a real source analysis; discussion-only drafts do not fabricate them. A detailed diagram annex is separately selectable
for supported standard-format publications. Up to 20 selected files and 50 MB total
are accepted; each original file must also meet the 25 MB safety limit. Preview hashes,
sizes and types are rechecked before transfer.

GitLab, Jira and legacy GLPI have upload adapters. The supported GitHub Issues API
has no equivalent upload operation here, so file transfer is unavailable there.
Reports and individual role downloads remain optional; they are not implicitly attached.

Issue creation and file delivery have separate outcomes. A successful issue remains
recorded if an attachment fails. An uncertain write is never retried blindly. Use
**Verify existing publication** and inspect the target when necessary: delayed search
or insufficient permissions can prevent immediate reconciliation. An unstarted file
transfer may resume against an existing issue without creating another issue.

## Find history and remove an analysis

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

You can edit a short analysis title without replacing the original need. The history
retains messages, need revisions, captured references and result versions.

**Delete analysis** requires confirmation. Cancel active work and wait for its agents
and any publication to finish first. Deletion hides the analysis from active views;
it preserves published-ticket audit records and linked history. It is not secure erasure.
