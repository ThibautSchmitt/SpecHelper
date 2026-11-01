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

Choose **Launch deep analysis** when the subject is ready for independent checks.
The application captures the human need, factual answers, explicitly confirmed business
decisions, attachments, environment documents and Git references for that cycle.
Exploratory AI hypotheses are not promoted to verified facts.

The roles execute sequentially inside the analysis:

1. **Analyst** investigates the need and authorized sources.
2. **Counter-analyst** performs an independent initial investigation, then confronts
   findings and searches for omissions, contradictions and counterexamples.
3. **Verifier** checks evidence and unresolved issues before a result is accepted.

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

## Prepare and publish a ticket

**Prepare a ticket** opens an editable draft in the conversation. It never starts
the three roles or publishes anything. You can save, copy or download the draft
without an analysis, after an interruption or with incomplete checks; it remains
explicitly unverified in those cases. Saved drafts are shared with the conversation
and reject conflicting edits from another browser.

The most recent user question is selected by default. **Ticket subject** lets you
choose another question without merging unrelated subjects. The initial draft
reuses that subject's stored discussion answer, code references and any public
interim role findings, even if no deep cycle produced a result. Clarification
answers use the user's answer text rather than copying the assistant's question.
Invalidated replies are excluded. Saved manual edits are preserved on reopening.

Choose **Write from conversation** for a concise, structured ticket written by the
conversation's selected assistant. This is a single queued drafting turn, using
its native session when available and the existing quota/cancellation controls.
It uses the selected subject, recorded answers, public role reports and relevant
source results; it does not run the three roles or claim new verification.
The title and body are saved back into the draft. Concurrent manual edits cannot
be overwritten by a delayed generated answer. Opening, selecting a subject or
saving by itself never invokes an AI.

When an analysis result exists, preparation also records its version and scope.
Discussion findings and later proposals are not promoted to verified findings.
Indicate whether the later exchanges concern the same need, a minor clarification
or a significant change. This assessment does not certify a proposed solution.
You can keep preparing immediately, or explicitly choose **Update analysis**.
That action saves and freezes the edited proposal as an unverified input for a
new independent cycle. Opening, editing or saving the draft never triggers it.

The preparation draft is separate from destination-specific publication drafts.
External publication retains the existing change-analysis workflow and requires
completed mandatory checks and non-blocking verified evidence. Question-only
conversations and incomplete analyses can still save and export their preparation
drafts. **Prepare a change** retains the existing linked-evolution path for a
question result; its source question and evidence remain available.
Changing the verified need requires reassessment before an earlier result
can be published. Editing a ticket does not independently verify those edits.

Select an enabled, verified connection associated with the environment, then a
destination accessible with that account. Multiple accounts of the same provider
remain separate choices. An unavailable account stays visible but cannot be selected;
a failure never silently switches accounts. If none is associated, follow the link
to the environment’s **Publication destinations** configuration. Choose the
standard concise format or a real destination template, complete mandatory fields,
edit the draft and inspect the preview. **Use prepared draft** explicitly copies
the saved conversation draft into the destination preview, including its verification
notice and source limitations; it never replaces a saved publication draft silently.
Draft edits persist separately from the
immutable result and reject stale concurrent changes. Publication happens only after
an explicit **Create ticket** confirmation; no agent publishes on your behalf.

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
when the destination supports uploads. A detailed diagram annex is separately selectable
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
**Tickets** lists confirmed publications and their source analysis/version; failed or
uncertain attempts remain accessible from the analysis and Activity.

You can edit a short analysis title without replacing the original need. The history
retains messages, need revisions, captured references and result versions.

**Delete analysis** requires confirmation. Cancel active work and wait for its agents
and any publication to finish first. Deletion hides the analysis from active views;
it preserves published-ticket audit records and linked history. It is not secure erasure.
