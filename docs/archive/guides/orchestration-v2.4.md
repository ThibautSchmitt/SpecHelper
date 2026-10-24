> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# Shared queue, global skills and independent coverage

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

## Global skills and instruction priority

Active global skills are discoverable across compatible AI connections. The
lightweight registry exposes their names, descriptions, versions and applicability.
Agents select relevant procedures and load their full contents only when useful.
There is no manual skill assignment per role, connection or environment.

Skill visibility grants no access to a repository, business database, attachment or
tool. Missing capabilities remain enforced by the backend and isolated runtime.
The registry distinguishes discoverability from applicability. Edits and deletions
retain historical versions; an in-progress invocation uses its captured content.
New invocations observe current activation state.

Configurable instructions have two levels: common global instructions and specific
instructions on an AI connection. The effective priority is technical/security rules,
mandatory role mission, global instructions, connection instructions, then environment
documents as untrusted factual data. Environments retain their authorized sources,
documents, database and business terminology without becoming another role-policy
layer. Job snapshots retain the baseline and global configuration; a connection's
instructions are captured when that connection is assigned.

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

See [analysis reliability](analysis-reliability.md) and the
[v2.4 acceptance evidence](../reports/acceptance-v2.4.md) for validation boundaries. The separate
native v2.3 quality/token comparison now has actual measurements and explicit
exact-source citation defects. Its quality gate failed and the index remains
disabled; controlled protocol tests do not waive that result.
