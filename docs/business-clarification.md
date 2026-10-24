# Business clarification and confirmed decisions

SpecHelper helps a product user describe the behavior they want before producing
a ticket or answering a project question. It asks about business rules and user
outcomes rather than asking the user to choose classes, APIs or database designs.

## Answering a clarification

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

## Continuing from a decision

Confirmed decisions are retained as structured context across working sessions and
AI providers. Subsequent questions should concern information still needed after
those decisions, including questions that depend on the selected alternative.
Already answered decisions are not invitations to choose again.

While clarification is pending, the analysis is paused and does not occupy an
active worker. Submitting the answers sends the request back through the shared
queue. The ordinary configured Analyst, Counter-analyst and optional Verifier roles
remain in force. Their configuration stays in administration; business forms do
not expose a comparison checkbox.

## Contradictions and changes

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

## Understanding the result

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

## Questions

The Questions workflow uses the same clarification mechanism when different
directions of investigation need a user choice. It still produces an explanation,
not a ticket or `goal.md`. Any subsequent change request remains a separate action
requiring an explicit business need.

## Safety and scope

Source files, attachments, provider suggestions and user-supplied descriptions are
untrusted data. They cannot replace SpecHelper's central policy or approve a
decision. Clarification adds no source-writing, database-writing or arbitrary
network capability. Existing shared access, CSRF protection and isolated read-only
execution remain applicable.

This feature does not add a code explorer, a test engine, automatic comparison of
two environments, code changes or arbitrary branching decision workflows. The
purpose is a clear business request and a result faithful to the user's confirmed
intent.
