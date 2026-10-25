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

## Outstanding validation

The current implementation is groundwork, not completed qualification. Human
review of expected answers and business coverage, actual comparative runs through
the application pipeline, independent review of those outputs and browser
acceptance remain outstanding. The harness does not itself execute native AI
comparisons. Synthetic tests do not establish accuracy on real business requests.
