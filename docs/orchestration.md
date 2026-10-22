# Analysis roles and verification

Business forms contain no comparison checkbox. New requests and questions
automatically use the instance policy and enabled authenticated assistant roles.
A compared analysis runs one analyst and one counter-analyst, followed by an optional
verifier. Connecting more assistants does not create more analyses or a voting panel.
The internal writer produces request ticket/goal artifacts or a question explanation;
it is not a fourth public role.

## Administration

Open **Settings → AI & Agents**. The analysis policy enables independent
counter-analysis for newly created work items; existing items keep their recorded
choice. Each connection can hold any combination of
**Analyst**, **Counter-analyst** and **Verifier**. Model, account availability and quota
continue to come from its named assistant configuration.

Global settings define role instructions, active internal functions, default skills,
invocation/time limits, verifier activation and permission for same-family fallback.
Understanding, source analysis and writing remain required internal functions.
Connection instructions add to the inherited instructions. Skill overrides store only
explicit enable/disable decisions; an empty override inherits the global selection.

Instructions cannot grant repository or business database write access. The runtime
still imposes read-only sources, isolated writable contexts and filtered database
capabilities. No setting enables development, branches, commits, PRs or automatic
ticket publication.

## Assignment and independence

At each public-role boundary, SpecHelper rechecks allowed roles, availability and
quota. It prefers a different actual model family from the previous role and an
unused family for verification. Two accounts running the same family do not provide
diversity. Current terminal adapters represent OpenAI and Anthropic families; a
third-family selection rule is covered by a controlled future-provider fixture,
without claiming an additional installed provider.

With two eligible families the sequence is normally A → B → A. With one family,
same-family fallback uses separate sessions and displays a limited-diversity warning,
when allowed. Otherwise the request waits explicitly for an eligible different family.

Each role gets a new terminal context with its own temporary files and conversation
history. The counter-analyst first examines the same business dossier and pinned
source SHAs independently. Only after that report is complete does it receive the
analyst's structured conclusions for comparison. The verifier receives structured
reports and references, not another agent's private notes or reasoning transcript.

## Bounds, recovery and review

At most one targeted evidence check is allowed. Invocation and time budgets remain
bounded; exhaustion is reported as an interrupted analysis. Validated checkpoints
remain recorded while an unavailable role waits or a failed connection is replaced.
Fallback is visible in the request history and queue. A resumed role receives a fresh
isolated context and explicit observations rather than a forked private history.

Human clarification starts a fresh analysis generation with new role contexts.
Completed business/attachment facts can be retained, but source conclusions that
could depend on the new answer are reassessed. Published versions stay immutable.

Queue cards show the current role, connection and model. Request details show role
steps, evidence summaries and diversity/availability warnings. The verifier's result
is an AI evidence check, never business approval. A person must review the ticket
and goal.md; external publication still requires its separate explicit confirmation.
