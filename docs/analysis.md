# Analysis, evidence and results

This is the reference for current Request/Question execution, independent review,
clarification and evidence. [Configuration](configuration.md) owns setup and skills;
[ticket publication](ticketing.md) owns external creation and delivery.

## Start and read an analysis

Choose an environment, describe the need or question in free text, and optionally
attach files. No initial type or comparison switch is required. Requests produce
a concise `ticket.md` and detailed `goal.md`; Questions produce `answer.md`.
Select a result version to copy or download immutable files. Continue the discussion
for a new version; changing instance settings never rewrites old files.

Start from **Home** without selecting a Question/Request type. The requirement
stage infers whether to explain existing behavior, prepare a change or address
both. Mixed intent keeps the existing behavior distinct from the desired change.
**Analyses** provides one search/list with light type, status and environment
filters, stable pagination and links ordered by actual discussion/result activity.
Home's counts and resumable items come from the same persisted records.

The detail page shows business conclusions, important limits and pending questions
before optional evidence. The chronological history retains the original need,
clarifications, answers, confirmed decisions, result versions and linked changes.
Git/DB receipts and tool/agent execution details remain expandable.

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
ready invocation, allowing different jobs to use different available AI connections
while each job remains strictly sequential. The mandatory public roles remain
Analyst, Counter-analyst and Verifier; requirement clarification, source inspection,
focused checks and final writing are checkpoints within that workflow.

## Step execution and capacity

Each invocation has a persistent execution attempt and its own reservation. The
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

Open **Questions**, select an environment, ask a question and optionally attach
files. No initial question type is required. Independent
analysis, counter-analysis and verification are mandatory and respect eligible assistant roles. A question can ask about business rules,
source behavior, data flows or architecture; no development terminology is required.

Answer clarification questions when requested. Clarification may happen before or
during source exploration. Waiting for an answer releases the worker; answering
returns the question to the shared queue. The execution contract applies, including
separate contexts when one account performs all roles.

Each consolidated answer distinguishes verified facts, inferences and uncertainties,
with repository-relative paths, optional symbols, branches and frozen Git SHAs.
Use **Continue discussion** to refine the explanation. Each new answer is a separate
immutable version. Follow-ups keep useful history and the original Git baseline;
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
even when the attachment is excluded. Application data is shared with the trusted
team; these links do not create user-private spaces.

## Official external references

Analyses retain the independent Analyst, Counter-analyst and Verifier workflow.
Global instructions request official external documentation only when a need depends
on regulation, a standard, contractual reference material or version-dependent
external behavior. A purely internal code question does not require Web research.
The global instruction remains visible and editable in Settings; source access and
security enforcement belong to the backend/runtime.

### Environment hints

Settings → Environments → Environment context accepts up to twelve public HTTPS URLs
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
