> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# Analysis roles and verification

Current Requests and Questions use mandatory Analyst, independent Counter-analyst
and Verifier roles. The system role cannot be replaced by editable text or skipped
by self-approval. Distinct jobs can use free compatible connections concurrently;
each job remains sequential.

See [shared queue, global skills and independent coverage](orchestration-v2.4.md)
for scheduling, capacity, clarification, cancellation, recovery and evidence rules.

Configurable instructions now have two levels: global and connection-specific.
Skills form a global library with on-demand loading and recorded version usage.
The [library guide](ai-library.md) describes editing, history and assisted creation.
Previous role-text, skill-override and environment-selection data remain retained
for historical execution/audit; they do not configure current system missions.
