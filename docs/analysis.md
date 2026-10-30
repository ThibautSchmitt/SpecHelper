# Analysis, evidence and results

This is the reference for current Request/Question execution, independent review,
clarification and evidence. [Configuration](configuration.md) owns setup and skills;
[ticket publication](ticketing.md) owns external creation and delivery.

## Start and read an analysis

### One conversation, two phases

New dossiers from **Analyses → New analysis** start with **Start discussion**.
One assistant answers in a persistent CLI session. This is exploratory discussion,
not independent verification. Sending another message, reopening the page or asking
a follow-up after a result does not start the three-role pipeline.

**Launch deep analysis** explicitly freezes the current human messages, confirmed
decisions, documents and project references, then starts the existing Analyst →
Counter-analyst → Validator sequence. Each role has a fresh isolated context;
the discussion session and its unverified hypotheses are not supplied as established
facts. **Prepare a ticket** before any result selects change intent and launches
this same mandatory investigation. Publication still requires the existing human
review and explicit connector action.

The assistant appears with the application's star icon and configured instance
name. The thread retains Markdown responses, attachments and concise results.
One expandable progress message per execution shows observed work and its real
state; deep cycles retain their three recorded role states. See
[observed work and provider differences](work-progress.md). Material limitations of
a partial deep result remain visible. Detailed reports, exact provenance and the
optional **See the AI review** disclosure stay under **Analysis report**. Role
downloads are never attached automatically to tickets.

Subsequent discussion preserves the old result and its frozen references. A small
notice distinguishes new messages from that result's verified scope. Launch another
deep cycle explicitly when those messages need independent verification. A factual
clarification stays conversation context; only an explicit structured choice marked
as a business decision enters the normative decision ledger.

### Native continuation and recovery

| Provider | Native continuation used by the adapter |
| --- | --- |
| Codex | `codex exec ... resume <thread-id> -`, in the same private CLI home |
| Claude Code | `claude --resume <session-id>`, in the same private CLI home |
| Antigravity | `agy --conversation <conversation-id>` with stream JSON, in the same private CLI home |

CLI command contracts are covered by runtime fixtures; that does not establish live
subscription access. An unavailable account or exhausted quota cannot be described
as a successful live-provider test. The provider must return a real native session
ID. Ordinary continuation sends the latest turn rather than replaying the whole
conversation. A new accepted analysis summary is supplied once, explicitly bound
to its frozen references.

An explicitly missing/expired native session or its storage limit allows one fresh
context with a visible recovery notice. Recovery uses the application history and
frozen project context, with older omitted context identified to the assistant when
the bounded recovery window is exceeded; the stored user history is never removed.
Other provider/transport failures are errors, not invented answers or silent session
replacement. The connection, account identity, model and effort remain pinned;
configuration changes require an explicit new session. Quota waiting does not rotate
to another assistant. Cancellation retains the provider reservation until the runtime
acknowledges the exact attempt stopped, and late outputs cannot enter the thread.

### Ownership and historical compatibility

The current deployment has shared instance authentication, not individual human
accounts. New unified conversations use a signed, HttpOnly browser-owner cookie:
their lists, legacy aliases, mutations and downloads are restricted to that owner.
Keep that browser profile/cookie to reopen them. Clearing it or using another browser
does not establish the same identity; there is no cross-browser account recovery UI.
Sessions are additionally isolated per conversation and frozen environment. This is
browser-session separation, not an individual-account authorization system.

Migration `0042_persistent_discussion` adds one JSON state field and the `DISCUSSING`
status, with no new table and no historical rewrite. Existing dossiers keep their
original shared visibility and immutable results. Opening them through Analyses
allows a new discussion session; historical direct Request/Question API contracts
remain compatible. Their completed analyses are not replayed automatically.

Home separates analyses needing an answer or recovery action, available results
(including explicitly partial results), and active work into mutually exclusive
categories. Each shows a few recent items and a filtered **See all** link.
Analyses retains the shared search, type/status/environment filters and history.
Review Home's usefulness after actual team use; this change does not remove it.

**Activity** starts closed in browsers without a saved preference and remembers
manual opening/closing across pages and reloads. Its badge counts only actionable
clarifications and failures, including scope questions before any job exists.
Running work has a separate animation, never an action count. Its attention indicator remains visible; clarification
waits never count as active AI work. Recorded step intervals provide active AI time;
older runs without intervals retain an unknown measurement. Business-answer waits
start at the saved clarification checkpoint. Queue waiting time is displayed only
when the latest admission time is known, without estimating resumed-job waits.
Up to five recent completed cards can be expanded; analysis history remains in Analyses.
Activity cards contain only business status, timing and actions. Execution diagnostics
and safe retry actions remain on the analysis detail page.
These are read-only presentation fields and do not change execution or scheduling.

Home also offers a short question launcher. It carries the text to the existing
new-analysis form through tab-local session storage, without putting business text
in the URL or starting an AI call. Environment selection, attachments and explicit
submission remain on Analyses. If storage is blocked, the text remains visible.

Choose an environment, describe the need or question in free text, and optionally
attach files. No initial type or comparison switch is required. Requests produce
a concise `ticket.md` and detailed `goal.md`; Questions produce `answer.md`.
Select a result version to copy or download immutable files. An explicit new deep
cycle creates another result version; changing instance settings never rewrites old files.

Start from **Analyses → New analysis** without selecting a Question/Request type. The requirement
stage infers whether to explain existing behavior, prepare a change or address
both. Mixed intent keeps the existing behavior distinct from the desired change.
**Analyses** provides one search/list with light type, status and environment
filters, stable pagination and links ordered by actual discussion/result activity.
Home's counts and resumable items come from the same persisted records.

## Delete an analysis

Open the analysis and choose **Delete analysis**, then confirm. Cancel or Escape
leaves it unchanged. Running and queued analyses must first be cancelled; deletion
waits for their agents to stop and release their reservations. A ticket currently
being published also blocks deletion.

Deletion removes the dossier from Analyses, Home and Activity and prevents access
through its current and legacy analysis URLs, including result downloads. This is
a logical deletion: records, attachments and immutable evidence are retained for
publication provenance and linked evolutions. Published tickets remain available
in Tickets and on the external platform; their details indicate that the source
analysis was deleted. There is no restore or physical data-purge action in the UI.

The detail page opens as a **business conversation**: the original need, actual
clarifications and answers, follow-ups and versioned conclusions share one thread.
Pending questions appear once with the existing guided choice/free-text controls.
The reply composer continues from the latest result and preserves revision checks,
scope admission and immutable previous versions. Older conversation ledgers remain
readable. When message metadata predates role attribution, SpecHelper matches the
saved question identifiers/text to accepted structured reports and their recorded
execution intervals, within the same human-answer cycle. It uses the original
provider/session snapshots, never today's connection configuration. Ambiguous or
incomplete history stays unattributed. This read-only projection does not rewrite
messages, restart analyses or make additional AI calls.

The conversation uses a plain assistant icon and the configured name for enabled discussions. User
messages have no avatar or "You" label. Clarification provenance stays in recorded
history rather than an extra disclosure in the thread. Explicit role mentions can
still appear as colored tags without adding separate speakers.

Each investigation cycle has one expandable progress message, keyed to its saved
run. Polling updates that same message instead of appending agent announcements.
Resumed progress appears after the latest user message for that investigation;
display ordering never rewrites saved timestamps. Prompts include the latest actual
answer separately from the older question it answered. Informational questions
investigate current behavior rather than requesting approval of future rules.
When an answer invalidates completed checkpoints, their evidence is retained in
history and their completion fences are invalidated before reanalysis. The
no-progress guard still rejects repeated or empty transitions within current work.
Comparison responses must keep status, verification requests and business questions
consistent. The existing single format-correction attempt uses review-specific
instructions; contradictory approvals are never accepted by dropping a check.
The triangle exposes Analyst, Counter-analyst and Verifier stages. A green check
means execution finished, not that the conclusion is guaranteed correct. Recorded
quota, authentication, model or busy states explain resource waiting; unavailable
evidence remains unknown. A completed partial investigation stays explicitly partial.

The conversation shows stage status and the accepted final synthesis, including
its business explanation and important remaining limits. Preliminary agent reports
are not concatenated into a second answer or presented as an agent conversation.
The assistant uses a plain icon without an avatar frame. The progress block stays
compact, with one row per role and no review or diagnostic panels inside it.
Explicit role names in assistant questions and prose appear as small colored tags;
the instance remains the single speaker. Tags do not infer attribution, alter user
messages or decorate code identifiers.

After a result is available, **Analysis report → Individual AI reports** offers an
optional Markdown download for each role with recorded findings. Each file contains
its saved summaries, findings, source references, agreements, issues, limits and
available connection/model provenance, tied to that result version and run. Missing
reports are not reconstructed. These downloads contain public recorded fields,
not runtime transcripts, prompts or private reasoning. They are created locally
on demand, trigger no AI invocation, and are never included in ticket publication.
Analyst and counter-analyst still investigate in separate contexts before comparison.
All three roles can suspend their current step for a necessary human clarification;
the existing decision ledger and repeated-question validation remain authoritative.

The progress message keeps the mandatory role sequence expandable. A clarification,
missing stage or partial result never becomes a verified conclusion merely because
a technical invocation ended. Important limits from the final accepted result
remain visible in its single response.

Final response actions open the existing **Analysis report and deliverables**,
prepare a reviewed ticket, start a linked change or copy the concise response.
Reports, diagrams, confirmed decisions, documentation generation, `goal.md`,
Git/DB receipts and exact execution provenance remain in expandable details.
Markdown documentation is generated only on explicit request through the existing
version-bound workflow; this change introduces no automatic PDF or extra AI calls.

Titles are proposed locally from the first sentence/line, without an AI call.
**Edit title** changes only the presentation title (up to 160 characters), never
the original need, decisions, baselines, results or their history. Editing is
temporarily unavailable during queued/running work to avoid concurrent worker saves.

Results show diversity from the recorded completed Analyst, Counter-analyst and
Verifier steps of that result's run: three families, two families, or one family.
A missing role means incomplete verification; absent family metadata stays unknown.
Independent sessions of the same family do not count as different families, and
diversity is never a confidence score.

## Need revisions and linked changes

**Edit the need** appends a dated business revision. It preserves the original,
confirmed decisions, earlier answers and immutable results, then starts a fresh
independent review cycle after scope admission. A blocked scope assessment remains
recoverable without calling an assistant. A running or validated analysis requires
the existing safe completion/reopening action before editing.

The old result remains readable but is marked for reassessment and cannot approve
or publish the updated need. A new result clears that stale-result warning. Edits
check the expected need, decision and result revisions; repeated submission ids do
not create another revision or job. Existing scope reformulations also enter the
dated need history.

**Evolve this behavior** opens a new objective linked to the selected answer version.
Its attributed summary and optional context document retain source hypotheses and
verification limits. The user writes the actual change. The new analysis freezes
the chosen environment's current Git references and runs the same three roles in
independent contexts. Creation retries, including a lost response followed by a page
reload, reuse the operation id. A distinct explicit submission may create another
legitimate child. Older answers and external tickets are never rewritten.

## Explanatory diagrams

The analyst and blind counter-analyst may propose useful structured business or
technical diagrams. Simple questions use no diagram. The counter-analyst searches
for omitted branches and dependencies independently before the proposals are compared.
The verifier checks every relationship's label, direction, meaning and source claims.
An unreviewed relationship omits the whole diagram with an explicit limitation;
Mermaid syntax alone never establishes correctness.

Existing relationships require supported Git/SQL claims with accepted provenance.
Hypotheses and proposed changes retain distinct labels and dotted flowchart edges.
Generic business/component labels exclude contact details, configured secrets,
raw identifiers and executable Mermaid directives; the independent review also
requires nonpersonal wording. No raw database rows belong in diagrams.

Diagrams are collapsed initially. Open one to see a locally rendered image, its
readable alternative explanation, zoom controls, relationship checks and a copyable
Mermaid source. A rendering failure leaves the explanation and source accessible.
The source is stored with the immutable evidence/report and `goal.md`; `ticket.md`
excludes it by default. An optional external file annex follows the separate
[ticket consent and destination restrictions](ticketing.md#attachments-require-explicit-consent).

## Execution contract

Requests and Questions use one persistent queue. Scheduling operates at the next
ready invocation, allowing different jobs to share available account execution slots
while each job remains strictly sequential. The mandatory public roles remain
Analyst, Counter-analyst and Verifier; requirement clarification, source inspection,
focused checks and final writing are checkpoints within that workflow.

## Step execution and capacity

Each invocation has a persistent execution attempt and its own slot reservation.
Several conversations can use one account concurrently, within the shared account
and instance limits in [deployment settings](operations.md#concurrent-conversations-and-analyses).
A conversation still has one active operation and isolated native sessions. The
scheduler chooses the oldest runnable job with a compatible connection, considering
allowed roles, actual availability, known shared account/quota capacity and model
family preferences. Waiting jobs do not reserve future roles or prevent another
compatible job from advancing. Distinct model families are preferred; reusing one
family uses independent contexts and remains explicitly qualified.

An invocation result is persisted before the next invocation starts. Replay uses
validated cached checkpoints rather than repeating completed analysis. A job awaiting
a user answer releases capacity. Answering an unanswered business question resumes
the same job and retains unaffected completed checkpoints. Replacing a confirmed
rule invalidates dependent analysis rather than silently reusing an obsolete result.

Cancellation, stale attempts and interrupted subprocesses require explicit states;
they must not produce duplicate publication or turn a partial execution into a
completed analysis. Elapsed time is observed time, not a predicted remaining duration.
There is no fixed five-minute business deadline. Technical SQL/tool timeouts,
resource limits and protection against stuck processes and repeated loops remain.

## Omission discovery and evidence

The independent Counter-analyst starts from the need and authorized sources before
receiving the Analyst's findings. Correct initial claims do not establish adequate
coverage. Both explorations provide concise inspected areas, newly discovered
elements and unexplored zones. Findings distinguish factual error, omission,
unverified hypothesis, interpretation disagreement, business choice and additional
evidence. Relevant indirect callers, configuration branches, historical states and
populations must be considered without claiming exhaustive coverage.

The comparison passes those structured concerns to the Verifier. The Verifier also
looks for essential points omitted by both explorations. Every material concern
needs an explicit resolution tied to supported final evidence or a frozen confirmed
business decision. Missing, unverified or unsupported resolutions remain blocking
limits. A necessary business choice returns to explained clarification before the
writer runs; the application does not select the policy itself.

The existing evidence contract remains: actual frozen Git source and excerpts, or
service-authored authorized SQL receipts; conditions, observation period, population,
sample limits, counterexamples and qualified status. Finite observations cannot
certify a universal claim. Historical anomalies do not establish present application
permissions. No business database means real business records were not checked.

## Evidence and scope

For a claim such as “all orders can be cancelled,” identify the subject, universal
quantifier, applicable time, population, configuration and exceptions. Search for
counterexamples and alternate entry points. A branch guarded by configuration does
not establish an unconditional rule. An older import or historical anomalous row
does not establish what current validated code allows.

A configured database can corroborate or contradict a material claim through
small counts, existence checks or distributions. It remains optional: unavailable
access, absent data and inconclusive results must be disclosed. Never request
unnecessary business rows merely to make an answer appear stronger. Credentials
remain outside prompts, sources remain read-only, and existing capability and
environment restrictions continue to apply.

If a material contradiction remains, perform a targeted check or request guided
business clarification. An unresolved business decision stays explicit; a reviewer
must not silently select a policy. Technical facts and a user's intended business
rule are different forms of evidence.

Exact Git evidence uses the authorized repository, frozen commit, path, line range
and literal excerpt. SQL evidence requires a service-authored authorized query receipt.
A database baseline identifies a connection, not a snapshot of its data. Claim scope
records environment, conditions, period, population and limitations; missing or
mismatched material scope cannot remain verified.

## Execution state and result completeness

A finished process does not imply a complete result. The task panel groups each
business item's roles in one card, running work first and completed work collapsed.
Successful Git synchronization is omitted there; its diagnostic history remains in
Settings. Waiting for AI capacity and waiting for a human answer are distinct.

| Result | Meaning and action |
| --- | --- |
| Complete | Required checks finished and retained claims satisfy evidence gates; review the business outcome. |
| Partial | Material uncertainty, contradiction, scope or missing verification remains; read limits and investigate. |
| Unusable/error | No usable completed result is available; inspect the failure and retry when appropriate. |

A READY label alone cannot authorize publication. Partial drafts may be inspected,
but missing mandatory checks or unsupported material claims block new external
publication and business validation. Downloads do not upgrade reliability.
Use **Cancel** to stop the current attempt, then **Retry** after it has stopped;
validated checkpoints and prior result versions remain retained. Historical execution
contracts may require starting a new analysis to use current cancellation controls.

## Clarification and confirmed decisions

### Answering a clarification

Start a request with the environment and business need. Add relevant documents or
screenshots when useful. The assistant identifies missing information,
contradictions and assumptions that can change the expected outcome or acceptance
criteria. A clear request can continue directly to analysis.

A clarification may use either:

- A free-text question when the answer is open or the available evidence does not
  support concrete alternatives.
- Two or three concrete options when the assistant can explain useful business
  alternatives, together with an **Other / Clarify** response.

Each concrete option describes the user-visible behavior, why it fits, its benefits,
limits and business consequences. These explanations appear beside the choices.
An option is a suggestion, not an established fact or an automatic decision. No
choice is imposed by the AI.

For example, when a contract still has benefits in progress, a clarification could
offer to block termination or allow termination with a warning. The choice belongs
to the user. Choosing **Other** requires a nonempty description of the desired rule.
That description becomes part of the structured decision used by the analysis.

Use the keyboard to navigate the radio options and the associated free-text field.
Review all answers before confirming them. Incomplete or stale submissions do not
silently change an existing decision.

### Continuing from a decision

Confirmed decisions are retained as structured context across working sessions and
AI providers. Subsequent questions should concern information still needed after
those decisions, including questions that depend on the selected alternative.
Already answered decisions are not invitations to choose again.

While clarification is pending, the analysis is paused and does not occupy an
active worker. Submitting the answers sends the request back through the shared
queue. The mandatory roles in the execution contract remain in force. Configuration
stays in administration; business forms do not expose a comparison checkbox.

### Contradictions and changes

A new answer can conflict with an earlier confirmed rule. SpecHelper explains the
previous rule and the proposed replacement before changing the retained decision.
The user can confirm the change or review the choice. An AI proposal cannot approve
its own replacement of a business rule.

Before business validation, a user can revisit a decision. A confirmed replacement
creates another decision-history entry and queues a focused reanalysis of the
affected conclusions. Prior decisions and generated result versions are retained.
The history records their order and the result versions that used them.

Business validation applies to the reviewed current result. To make further
changes after validation, explicitly reopen the request first. This protects the
accepted rule set without rewriting historical results. A stale browser cannot
approve or revise a newer result without refreshing its version.

### Understanding the result

Where the inspected information supports it, the result separates:

- **Current behavior:** what happens today.
- **Desired behavior:** what the user wants to happen.
- **Gap:** the difference to resolve.
- **Business impacts:** consequences for users, operations and business rules.

Missing or unverified information remains an uncertainty. A summary should not
present an assumption as an observation or require code identifiers to understand
the business outcome.

The concise ticket retains the latest confirmed decisions as requested rules and
acceptance criteria, together with remaining uncertainty. It does not reproduce the
whole discussion. The corresponding `goal.md` can retain detailed decisions,
technical context, source references and implementation constraints for a coding
agent. Both artifacts belong to an immutable result version.

Confirmed values are carried into the artifacts independently of the writer's
prose. Exact known superseded rules are removed from normative result fields.
This does not prove general semantic consistency: review the result, including its
remaining assumptions, before business validation. If all confirmed rules cannot
fit the concise ticket contract, SpecHelper requires shorter wording or a split
request instead of silently removing decisions.

When viewing an older result, its decisions and summary come from that version's
snapshot. The current live decision history does not replace those historical
values. Publishing an external ticket continues to require a separate reviewed
publication action for the exact result version.

## Questions and request handoff

### Explore a project

Open **Analyses → New analysis**, select an environment, ask a question and optionally attach
files. No initial question type is required. Discussion uses one assistant; explicit deep
analysis requires independent analysis, counter-analysis and validation with eligible assistant roles. A question can ask about business rules,
source behavior, data flows or architecture; no development terminology is required.

Answer clarification questions when requested. Clarification may happen before or
during source exploration. Waiting for an answer releases the worker; answering
returns the question to the shared queue. The execution contract applies, including
separate contexts when one account performs all roles.

Each consolidated answer distinguishes verified facts, inferences and uncertainties,
with repository-relative paths, optional symbols, branches and frozen Git SHAs.
Use the conversation to refine the explanation. Each new deep result is a separate
immutable version. Discussion follow-ups keep native history and the frozen Git baseline;
start a new question to explore a newly synchronized source revision.

### Copy or document an answer

Select the answer version you want. **Copy explanation** copies its exact stored
Markdown, including references and verification limits. The same content can be
downloaded as `answer.md`.

**Create documentation** offers three formats:

- **Business:** observed behavior, rules, steps, examples and points to confirm.
- **Technical:** implementation, dependencies, flows, files, symbols and Git references.
- **Mixed:** business explanation followed by technical detail.

These formats organize the selected answer's analyzed facts without a second
analysis pipeline. If details are missing, continue the question to obtain a more
complete answer before exporting. Documentation is Markdown; no PDF generator is
bundled. Each saved document retains its source question, answer version, language
and Git references. Generating a document never writes to a repository or third-party tool.

### Create a change request

Choose **Create a request** from a usable answer. The ordinary request form opens
with the source environment selected and a preview of an internal Markdown context
attachment. Change the environment if needed, and explicitly describe the desired
change: the need is intentionally blank. You can exclude the context before
creation or remove it from the draft before launch.

The context contains the original question, curated conclusions and rules, verified
facts, inferences, uncertainties and referenced files/symbols/branches/SHAs. It
records the source question and immutable answer version. It excludes the full
conversation, private agent reports and original attachments. Review this summary
before including it: a generated explanation may itself contain sensitive business
information. Configured credentials are redacted; invalid private filesystem paths
prevent export rather than appearing in a validation error.

On launch, the new request uses the ordinary clarification, analysis, comparison,
review and ticket/goal workflow. The transferred document is an isolated attachment
read on demand; its full text is not inserted into every prompt. It is untrusted
reference material, never an instruction with elevated priority. The agent must
reopen current sources and compare repositories, branches and SHAs before trusting
prior technical conclusions, especially after changing environments or synchronizing code.

Several requests can be created from one answer. Each has independent sessions,
results, frozen context and baseline. Later question answers never update an
already-created request's attachment. Links retain provenance in both directions,
even when the attachment is excluded. Historical data remains shared with the trusted
team. New private conversation links preserve browser ownership and do not grant access themselves.

## Official external references

Analyses retain the independent Analyst, Counter-analyst and Verifier workflow.
The native analysis method requests official external documentation only when a need depends
on regulation, a standard, contractual reference material or version-dependent
external behavior. A purely internal code question does not require Web research.
Native analysis instructions supply this method; source access and security
enforcement belong to the backend/runtime.

### Environment hints

Settings → Environments → Configured environments → Environment context accepts up to twelve public HTTPS URLs
or domains, each with an optional applicability note. These are non-exclusive factual
starting points, not role instructions or an allowlist. Saving a hint does not fetch
it. Changes use the context revision and do not alter existing frozen analyses.
Independent counter-analysis can consult different relevant official sources.

### Scoped reading

Only source exploration and verification checkpoints receive the public reference
reader. Requirement clarification, synthetic library demonstrations and final writing
do not receive it. Skills cannot grant this capability. An assistant may search for
public business concepts, then fetch primary pages through the scoped broker. Search
suggestions alone are not evidence. No research is performed merely by enabling the tool.

The reader supports HTML and plain text over HTTPS on port 443. It rejects credentials
in URLs, IP literals, private/mixed DNS answers, non-HTTPS redirects, unsupported
content types, compressed responses and oversized transfers. DNS is resolved and
validated once per connection; the TCP address is pinned while TLS verifies the
original hostname. Every redirect is checked again. No cookies, incoming headers,
provider OAuth or environment proxies are forwarded. Each invocation has bounded
requests, transfer size and read time. Some official sites require unsupported formats,
anti-bot interaction or authentication; those checks remain explicitly unavailable.

Public search sends its query to DuckDuckGo; page reads send the selected URL to the
publisher. Instructions prohibit sending private source text, records or identifiers.
Filtering prevents private-network access and credential forwarding, but is not a
semantic data-loss-prevention system. Do not treat arbitrary public page contents as
trusted instructions or execute downloads.

### Provenance and applicability

A fetched page creates a service-authored reference ID, normalized URL, title,
consultation timestamp, byte-content hash and bounded text observation/hash. The
runtime retains these independently of model declarations. Important Web claims cite
that ID and an exact short excerpt. Invented IDs, mismatched excerpts or altered
observations cannot support a claim.

An external claim records the authority attribution, effective date/version,
jurisdiction, scope and applicability notes. Missing or unverified applicability stays
a material limit. A regulatory rule without a stated effective date cannot establish
a current obligation. Publication date, where present in page metadata, is retained
separately and is not silently interpreted as an effective date.

The result labels official rules, external contractual references and deployment
observations separately. External documentation alone cannot prove actual deployment
behavior; frozen Git and authorized SQL observations remain the deployment evidence.
Dates/version strings and provenance checks do not certify a model's interpretation:
the independent review still has to assess authority, conflicts and applicability.

The history and exports retain the actual references and observation hashes. Final
writing receives concise verified claims and reference metadata, not entire copied
Web pages. No historical result or evidence is rewritten when a site changes later.

## Reliability limits

Controlled workflow tests prove application behavior for supplied responses, not
general live-model accuracy. File-read telemetry proves observed access, not
understanding. The native exact-citation gate failed; optional production indexing
remains disabled. See [known limitations](known-limitations.md) and the
[evaluation method and observations](index-evaluation.md).

The Home page is a compact resumption view. Create an analysis from **Analyses → New analysis**;
Home offers only a link to this form. Previous `/?new=1` and question-to-change links
redirect to the same analysis creation route while retaining their source version.
