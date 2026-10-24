> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# Questions and reusable context

Questions explain existing project behavior. Requests specify a desired change.
Both use the same environments, analysis engine, read-only sources and database
access, optional reference documents, attachments, assistant configurations and
persistent shared queue, ordered by oldest runnable job. Questions do not create tickets, goals or code changes.

## Explore a project

Open **Questions**, select an environment, ask a question and optionally attach
files. No initial question type is required. Independent
analysis, counter-analysis and verification are mandatory and respect eligible assistant roles. A question can ask about business rules,
source behavior, data flows or architecture; no development terminology is required.

Answer clarification questions when requested. Clarification may happen before or
during source exploration. Waiting for an answer releases the worker; answering
returns the question to the shared queue. The normal assistant availability and
comparison rules apply, including comparison through one connected account.

Each consolidated answer distinguishes verified facts, inferences and uncertainties,
with repository-relative paths, optional symbols, branches and frozen Git SHAs.
Use **Continue discussion** to refine the explanation. Each new answer is a separate
immutable version. Follow-ups keep useful history and the original Git baseline;
start a new question to explore a newly synchronized source revision.

## Copy or document an answer

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

## Create a change request

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

## Storage and compatibility

Questions reuse `Request` with `workflow=question`, existing messages, runs, jobs,
sessions, context manifests and versions. Question versions store a typed
`explanation` and only an `answer.md` artifact. `QuestionDocument` stores optional
immutable Markdown with its source version. Request and attachment source-version
links preserve provenance. Migration 0019 adds these fields without rewriting old
results; existing records default to the ordinary request workflow.

Source-version links protect referenced answers from deletion. Include questions,
answer documents and transferred attachments in normal application backups. The
existing source isolation, database permissions and attachment limits apply.
See [security](../../../SECURITY.md) and [acceptance evidence](../reports/acceptance-v1.7.md).
