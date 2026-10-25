# Product overview

SpecHelper prepares work for a trusted team using the sources of the application
they operate. It combines business clarification with independent technical exploration
and keeps the conditions and limits of the answer visible.

## Choose a workflow

| Need | Start with | Result |
| --- | --- | --- |
| Understand existing behavior, rules or dependencies | Questions | Sourced explanation, answer.md and optional documentation |
| Describe a change for implementation | Requests | Concise ticket.md and detailed goal.md for a coding agent |
| Create an external issue from a reviewed result | Publish ticket | Human-confirmed publication linked to the exact result version |

Select an environment, write in free text and optionally attach documents or screenshots.
There is no initial type or comparison selector. Clarification asks useful business
questions when the outcome depends on a decision you must make.

The ticket communicates intent, expected behavior, solution, impacts, risks and
acceptance criteria. The goal retains technical context, source baseline, files/symbols,
constraints and expected implementation checks. SpecHelper analyzes; it does not
implement the change or claim to have executed those future tests.

Questions explain observed behavior without creating tickets. A selected answer can
become business, technical or mixed Markdown documentation. To request a change,
open the ordinary Request form with an optional reviewed context attachment and
explicitly describe the desired change. Recheck transferred findings against new sources.

## Review and refine

[Analysis](analysis.md) owns independent roles, evidence, clarification and completeness.
Follow-ups create immutable result versions; old files and baselines remain available.
A finished execution can still produce a partial result. Review limits rather than
treating a status label as proof.

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

The established application baseline is v2.5; v2.6 consolidated its documentation.
The [Antigravity adapter](antigravity.md) adds Google-account authorization with
one verified live Gemini execution and explicit evaluation limits. Other future
proposals are not available product features.
