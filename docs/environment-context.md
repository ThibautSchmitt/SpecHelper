# Environment context

An environment can optionally supply business terminology, factual context and reference documents:
architecture notes, business terminology, conventions and constraints. Requests
continue to use their own separate attachments. No stack is assumed; actual sources
and installed dependencies determine the analysis. Environment text is untrusted
documentary data, not a third editable instruction level.

Open **Settings → Environments**, then expand **Environment context** for an
existing environment. Factual context accepts up to 4,000 characters and can be disabled
without clearing them. Keep Git and database credentials in secure connection
settings. Known configured credentials are rejected in factual context and text uploads.
This is an exact credential safeguard, not a general document classification service.

Upload up to 20 documents of 25 MB each. Supported formats follow request attachments:
Markdown, TXT, PDF, DOCX, PNG/JPEG/GIF/WebP, CSV, JSON and LOG. The panel shows the
name, media type, update date, size, version and SHA-256 hash. UTF-8 text has a bounded
preview; binary or invalid UTF-8 text is identified as unreadable. Other supported
formats are inspected using the runtime's document tools; extraction may fail for
corrupt or encrypted files and should be reported by the assistant.

Toggle a document to exclude it from future analyses without removing it. Replace
it to create a new immutable content version. Remove it to hide it from the current
configuration; historical analyses retain their files. Concurrent edits use a context
revision guard and require reloading when another browser has changed the context.

Launching an analysis freezes active references and factual context. Files remain
available for relevant, on-demand exploration; their contents are not copied into the
initial prompt. Clarification keeps these references while adding the new answers.
Continuing a completed discussion picks up current reference versions while keeping
the request's Git baseline. Deleted environments use the last recorded references.

The request detail shows the frozen references for every run and selected result
version, including historical downloads. Read observations come from runtime file
access, not assistant claims. A positive observation proves a read, not understanding;
an absent observation does not prove non-use. Memory-mapped reads can be missed,
and unsupported or incomplete telemetry is shown explicitly.

Analyst, counter-analyst and verifier receive the same reference versions. Their
private sessions remain separate. The initial counter-analysis receives the common
sources before the first analyst's conclusions are supplied for comparison. Typed
reports retain evidence, impacts, constraints and unresolved questions for handoff.

The analysis instructions require stale or contradictory documents to be identified
and inspected code to take precedence for questions about implementation. Tickets
remain concise, while `goal.md` preserves code paths, baseline SHAs and reference
version hashes for independent verification. Generated conclusions redact exact
configured Git/database credentials before schema validation and publication.
