# Project scope and qualification groundwork

Requests and Questions are checked before an AI provider is reserved or an
analysis job is queued. The deterministic policy uses the submitted text and
saved environment context. It does not open attachments, visit URLs or query
the analyzed business database to decide scope.

Clearly unrelated inputs require reformulation. Ambiguous inputs request project
context; an absent environment can be selected before analysis. Original input
and pending follow-ups are retained. Revision checks prevent silently replacing
scope edits made in another browser. These checks do not grant agent permissions.

## Qualification tooling

`scripts/qualification/` contains 24 authored synthetic cases, including a separate
reserve, source repositories, attachments and a finite database fixture. This is
not an anonymized production corpus or evidence of business representativeness.
Expected answers are separate from agent packets and require an explicit human
review by someone familiar with the business.

From the repository root, validate the checked-in fixture:

```sh
python3 -m scripts.qualification.harness validate
python3 -m scripts.qualification.harness --help
```

The harness prepares frozen Git/source/database inputs, checks their integrity,
exports a review document and records explicit human review. Comparison requires
at least two configurations and independently reviewed outputs bound to their
exact packets. Unknown token usage, billing costs and unreviewed semantic results
remain unknown. Missing mandatory independent stages cannot count as complete.
Keep generated studies and review receipts in private storage such as `.local/`.

## Independent exploration

The counter-analyst's first exploration receives the original need, confirmed
user choices and frozen project context. It does not receive the first analyst's
report or AI-generated requirement findings and understanding, which can already
contain code conclusions. Comparison receives both reports only after that
independent exploration finishes.

## Collect application results

Run corpus cases through the normal Request/Question worker in an isolated test
application database. Use only the authorized frozen fixture sources and database;
keep evaluator answers outside every agent workspace. Preserve required independent
stages and any business clarification instead of fabricating answers to finish a run.

`scripts.qualification.application` can enqueue the frozen inputs without invoking
AI itself. It requires PostgreSQL with `qualification` in the database name, an
instance name starting with `Qualification`, and `SPECHELPER_QUALIFICATION=1`.
Enable exactly the frozen provider/model for each role in that isolated instance.
Map its ready environments to the two fixture database states:

```json
{"available": 1, "absent": 2}
```

With that application's database environment loaded:

```sh
SPECHELPER_QUALIFICATION=1 PYTHONPATH=backend:. uv run --project backend \
  python -m scripts.qualification.application .local/study \
  --configuration gpt-first --environments .local/environments.json \
  --output .local/bindings.json
```

The default batch excludes the reserve. Select held-out cases explicitly with
`--cases` only after the protocol is final. The normal worker processes these jobs;
the command does not replace any analysis stage or independently call a provider.
Repeating the same command retains existing requests and does not queue them again.
Source/attachment mismatches and incompatible role configurations stop enqueueing.
Finish one distribution before switching role configuration for the next batch.

Record each actual request UUID in a bindings file:

```json
{"Q01": "the-actual-request-uuid"}
```

Record CLI versions from the binaries that executed the runs, separately from the
expected configuration. Each provider entry requires `version`, `observed_at` and
`source` (the command used to observe it). Never substitute a configured version
for an observation.

With the isolated application's database environment loaded, collect results from
the repository root using its backend dependencies:

```sh
PYTHONPATH=backend:. uv run --project backend python -m scripts.qualification.collect \
  .local/study --configuration gpt-first \
  --bindings .local/bindings.json --cli-versions .local/cli-versions.json \
  --output .local/run-gpt-first.json
```

The collector performs no AI inference. It rejects mismatched request text,
workflow, language, source SHA, attachments, database availability and explicitly
frozen instructions/skills. Actual database contents must also be held stable and
verified by the operator; a matching connection name is not snapshot evidence.
Running work remains running. Failed stages and legitimate human clarification
are partial outcomes. Their observed tokens and duration remain in the report.
Provider usage is recorded for failed responses and format repairs as well as
successful responses; missing counts stay unknown.
Measured subtotals are shown separately when some calls lack usage. Wall elapsed
time includes queue/operator delays; execution time sums persisted invocation
durations when all of them are available. Scope-only cases measure admission,
not a generated business answer or completion of the independent analysis stages.

The comparison keeps development and reserve results separate and rejects role
observations that differ from the frozen model, family, effort or CLI version.
Independent semantic review remains mandatory for error and omission counts.

Verification limitations can mention inaccessible runtime locations. Publication
replaces private paths in evidence prose with a neutral marker while preserving
the limitation, evidence status and blocking flag. Source excerpts and query/Web
receipts remain exact; this does not make an unverified claim supported.

## Outstanding validation

The current implementation is groundwork, not completed qualification. Human
review of expected answers and business coverage, the full comparative corpus run
through the application pipeline and independent review of those outputs remain
outstanding. Scope interface checks cover both languages, desktop/mobile,
attachments, concurrent edits and recoverable follow-ups. The harness does not itself execute native AI
comparisons. Synthetic tests do not establish accuracy on real business requests.
