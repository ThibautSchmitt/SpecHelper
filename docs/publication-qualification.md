# Opt-in publication qualification

This administrative bench reuses reviewed publication drafts and the existing
publication engine. It does not generate a draft, launch AI, revise pre-existing
ticket contents, delete a ticket, change connections or select another account after
an error. Selected uploads may append native attachment links to the test ticket.
Run it only against explicitly approved test destinations. Credentials stay in
SpecHelper's connection vault; the plan and report contain no tokens.

Real GitHub and Jira execution is deferred at the user's request. Support in this
bench is prepared for later qualification, not evidence that those platforms have
passed a real test. The current Jira adapter targets Cloud REST v3; the unlicensed
local Data Center setup is not a substitute for an authorized Cloud test project.

## Prepare and review

Create one neutral conversation-ticket draft per case through SpecHelper, select
an environment-authorized connection and destination, and save the exact final
publication draft. Select attachments explicitly and preserve their SHA-256
digests from the preview. Generated documents must already be ready and selected;
the bench never generates additional documents or sends unselected files.

Capture the publication draft's ID, revision, exact title and SHA-256 of its UTF-8
`body` (without newline conversion). Use a distinct, persistent UUID operation key
for each case. Preserve these keys after interruption: a new key is not a recovery
procedure. A resumed confirmed/uncertain operation is never allowed a new create.

For example, `.local/publication-qualification/plan.json`:

```json
{
  "schema_version": 1,
  "confirmation": "QUALIFY SPECHELPER PUBLICATIONS",
  "cases": [
    {
      "draft_id": "00000000-0000-4000-8000-000000000001",
      "revision": 1,
      "idempotency_key": "00000000-0000-4000-8000-000000000002",
      "platform": "gitlab",
      "scenario": "lost_response",
      "title": "Reviewed neutral qualification ticket",
      "body_sha256": "replace-with-the-64-character-description-digest",
      "attachment_sha256": [],
      "acknowledge_unverified": true
    }
  ]
}
```

The identifiers and digest above are placeholders. Use actual reviewed metadata.
`acknowledge_unverified` explicitly records whether publication without independent
verification was approved. It does not turn the document into verified evidence.
Review every case before supplying the confirmation string and execution flag.

## Execution

Run from the installation checkout after verifying no unrelated publication is
using the chosen test drafts. Mount only this script; pass the plan on standard
input and keep the output report on the host. Never mount the whole checkout or a
credential directory:

```sh
umask 077
cat .local/publication-qualification/plan.json | docker compose run --rm --no-deps -T \
  -e PYTHONPATH=/app/backend \
  -v "$PWD/scripts/evaluation/publication_qualification.py:/probe.py:ro" \
  backend python /probe.py \
  --plan - --report - --workers 2 --confirm-test-publications \
  > .local/publication-qualification/report.json
```

The plan permits one to ten cases; workers are bounded to 1–10 and default to two.
These are test HTTP concurrency settings, not changes to AI scheduling. Direct
`--report /path` refuses an existing report. With shell redirection, choose a new
filename yourself to preserve earlier reports. For recovery, retain the same input
keys and choose another report filename. An interrupted stdout report can be
incomplete; the original plan keys and SpecHelper's durable operations remain the
recovery source.

## Scenarios and evidence

- `double_confirmation`: two concurrent confirmations use the same operation key;
  a later confirmation must return the same publication, with one permanent
  conversation event and the selected connection/destination preserved.
- `lost_response`: the real provider accepts creation, then the bench deliberately
  drops its returned result before SpecHelper records success. Only the existing
  uncertain operation is reconciled, at most ten times with two-second intervals.
  Indexing delays may leave it uncertain; the bench never creates a replacement.

A process-local write fence blocks and reports any attempted second remote create
for a case. Therefore zero external duplicates alone is not a pass: the report must
also show no excessive `create_attempts`. This fence affects only the bench process,
not the running web application or worker. A resumed operation has a zero-create
budget; reports distinguish reused operations from newly exercised fault injection.

The report includes durations, publication IDs, confirmed external references,
safe URLs, connection IDs, response-loss observations and transfer counts. It checks
attachment delivery against the explicit selection. An uncertain upload remains
uncertain and fails qualification; it is never blindly retransferred. Errors retain
content-free categories rather than potentially sensitive provider response text.

GitLab, Jira and GLPI attachments remain subject to their existing discovered
permissions and size limits. The supported GitHub Issues REST connector does not
upload those files: its plan must select no attachments. The bench does not invent
an upload endpoint, create a gist or push files into a repository as a workaround.

A `PASS` on a resumed confirmed operation proves preservation/idempotence, not a
new provider creation or a newly injected network failure. Check the report's
`resumed_operation`, `response_loss_injected` and `create_attempts` fields before
describing coverage. Failure or interruption preserves drafts, publication history
and external tickets for inspection; there is no automatic cleanup or deletion.
