# Product overview

SpecHelper prepares work for a trusted team using the sources of the application
they operate. It combines business clarification with independent technical exploration
and keeps the conditions and limits of the answer visible.

## Start from Analyses

| Need | Start with | Result |
| --- | --- | --- |
| Understand existing behavior, rules or dependencies | Analyses → New analysis | Sourced explanation, answer.md and optional documentation |
| Describe a change for implementation | Analyses → New analysis | Concise ticket.md and detailed goal.md for a coding agent |
| Create an external issue from a reviewed result | Prepare ticket | Human-confirmed publication linked to the exact result version |

Select an environment, write in free text and optionally attach documents or screenshots.
There is no initial type or comparison selector. Clarification asks useful business
questions when the outcome depends on a decision you must make.

Home shows **Needs attention**, **Results available** and **In progress** items.
Partial results keep their explicit status and reported limits. **Analyses** brings questions
and changes together with search, environment/status filters and pagination. The
navigation also retains **Tickets** and the bottom-left **Settings** button.
Historical Question and Request URLs continue to open their original records.

The ticket communicates intent, expected behavior, solution, impacts, risks and
acceptance criteria. The goal retains technical context, source baseline, files/symbols,
constraints and expected implementation checks. SpecHelper analyzes; it does not
implement the change or claim to have executed those future tests.

Questions explain observed behavior without creating tickets. A selected answer can
become business, technical or mixed Markdown documentation. To request a change,
select **Evolve this behavior**. The new objective remains linked to the chosen
answer version, with its attributed summary and optional context attachment. Describe
the desired change explicitly; uncertain source conclusions remain uncertain. Its
independent analysis uses the selected environment's current Git baseline.

## Review and refine

[Analysis](analysis.md) owns independent roles, evidence, clarification and completeness.
Follow-ups create immutable result versions; old files and baselines remain available.
A finished execution can still produce a partial result. Review limits rather than
treating a status label as proof.

Editing a need appends a dated revision and retains the original, confirmed decisions
and previous results. Old conclusions are marked for reassessment and cannot be
published as the updated analysis. Useful diagrams explain reviewed processes or
dependencies; their sources remain in reports and development goals.

External [publication](ticketing.md) requires another reviewed step. Choose an actual
template/type or the short standard format, fill required fields and confirm the exact
preview. Detailed sections and selected files are optional; attachments start excluded.
Partial results cannot bypass missing verification through publication.

## Shared self-hosting

Connections and data belong to the trusted team instance. An environment combines
GitHub/GitLab repositories and branches, optional read-only PostgreSQL and factual
documents. No individual accounts, private workspaces or tenant boundaries are provided.
The [security policy](../SECURITY.md) owns access requirements; sandbox isolation
does not prevent authorized data from reaching the selected AI provider.

## Find a guide

- [Install and start](../README.md#quick-start)
- [Configure assistants, models, skills and environments](configuration.md)
- [Understand analysis and business decisions](analysis.md)
- [Publish tickets and recover uncertain delivery](ticketing.md)
- [Understand services/storage](architecture.md) and [operate/back up](operations.md)
- [Review known limitations](known-limitations.md) and [security boundaries](threat-model.md)
- [Find historical evidence](archive/README.md) or [future scope](roadmap.md)

The unified analysis experience builds on v2.5 ticket preparation and existing versioning.
The [Antigravity adapter](antigravity.md) adds Google-account authorization with
one verified live Gemini execution and explicit evaluation limits. The separate
[v2.8 qualification](qualification-v2.8-status.md) remains partial and deferred;
the interface changes do not establish new provider or business-accuracy results.
