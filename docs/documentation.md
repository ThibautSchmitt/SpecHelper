# Documentation maintenance

Documentation describes implemented behavior and its evidence. Code and observed
runtime behavior take precedence over an old report or an unimplemented target.

## Ownership by subject

| Reference | Owns | Link instead of duplicating |
| --- | --- | --- |
| [README](../README.md) | Product value, shortest installation path, guide navigation | Fine settings and internal architecture |
| [Overview](overview.md) | Home, unified analysis entry and output orientation | Execution rules |
| [Configuration](configuration.md) | Settings, connections, skills, models, context, appearance and language | Scheduling or publication recovery |
| [Interface](interface.md) | Shared visual conventions, surfaces, controls and accessible states | Analysis and publication behavior |
| [Analysis](analysis.md) | Mandatory roles, scheduling, clarification, evidence and completeness | Administrative instructions or platform templates |
| [Architecture](architecture.md) | Components, storage and technical trust-boundary implementation | Operations commands or policy |
| [Operations](operations.md) | Startup, upgrades, backups, diagnostics and runtime commands | Security policy and dated release totals |
| [Ticketing](ticketing.md) | Connector/API compatibility, drafts, consent, delivery and reconciliation | General orchestration |
| [SECURITY](../SECURITY.md) | Access/deployment policy and vulnerability reporting | Scanner results |
| [Threat model](threat-model.md) | Assets, permissions, retention, transfers and residual trust | Dated probe logs |
| [Security validation](security-testing.md) | Scanner gates, findings and exact expiring exceptions | A universal security guarantee |
| [Index evaluation](index-evaluation.md) | Evaluation method, measured results and activation decision | Production index support |
| [Known limitations](known-limitations.md) | Outstanding limits, implications and evidence still needed | Whole historical reports |
| [CONTRIBUTING](../CONTRIBUTING.md) | Development, verification and translation maintenance | Product instructions |
| [CHANGELOG](../CHANGELOG.md) | Delivered changes and links to original evidence | Another full specification |
| [Roadmap](roadmap.md) | Implemented/future status and qualification boundaries | Full feature instructions |

## Updating and archiving

Every functional change updates its thematic reference in the same delivery.
Every major delivery updates CHANGELOG. A document should link to the owner of a
rule rather than create another normative copy. Short product summaries may link
to the rule, but must not independently redefine it.

Do not add a permanent version-specific acceptance report by default. Use test
artifacts/CI and changelog links; retain a dated report only when non-repeatable
observations, migration preservation, a security decision or an explicit acceptance
requirement justifies it. State controlled/native evidence, date, tested revision,
actual failures and remaining limits separately.

Before moving or deleting an existing document:

1. Inventory its source, links, decisions, active facts and limitations.
2. Move current facts into the owning reference; retain open items in known limitations.
3. Preserve significant historical evidence in the archive with a historical banner.
4. Rebase links and run the checker across active documents **and** archives.
5. Review a content-preservation comparison and the diff before publication.

Never erase a security decision, unresolved failure, scan finding or expired condition
because its report is old. Never rewrite historical migrations to match current prose.
Archive snapshots are evidence for their original context, not active specifications.
The [inventory](archive/inventory.md) maps every pre-consolidation Markdown source.

## Checks and their limits

Run from the repository root:

```sh
python3 scripts/check_documentation.py
```

The standard-library checker validates local link targets, Markdown heading/explicit
anchors, shell-block syntax, named runtime modules and npm scripts. It scans root,
docs and GitHub Markdown; it excludes private/generated data and local agent instructions.
It does not fetch external URLs or execute examples, and it is not a full CommonMark
parser. Relative links must use ordinary Markdown link syntax or reference definitions.
Review any less usual syntax manually.

Run changed operational commands on disposable installations; a shell syntax check
does not prove behavior. The [clean installation observation](operations.md#installation-observation)
records executed startup, data isolation and caching boundaries. Existing runtime/
application test counts belong to their dated archive reports, not this documentation change.

## Technical consistency review

The consolidation checked current source rather than treating old reports as authoritative:

| Topic | Source inspected | Reference |
| --- | --- | --- |
| Per-step claim and compatible-job bypass | [worker.py](../backend/core/worker.py), [step_execution.py](../backend/core/step_execution.py) | Analysis execution contract |
| No fixed total deadline on current protocol; technical guards retained | [analysis_flow.py](../backend/core/analysis_flow.py), [step_supervisor.py](../backend/core/step_supervisor.py), [server.py](../runtime/server.py) | Analysis and operations |
| Global skills, capability metadata, captured instructions | [global_skills.py](../backend/core/global_skills.py), [skill_metadata.py](../backend/core/skill_metadata.py), [step_execution.py](../backend/core/step_execution.py) | Configuration |
| Free-text entry and publication-only template selection | [work-item-form.tsx](../frontend/src/components/work-item-form.tsx), [ticket_presentation.py](../backend/core/ticket_presentation.py) | Overview and ticketing |
| Partial-result and independent-check gates | [analysis_evidence.py](../backend/core/analysis_evidence.py), [ticket_publication.py](../backend/core/ticket_publication.py) | Analysis and ticketing |
| Compose settings, automatic migrations, port/bind and volumes | [compose.yaml](../compose.yaml), [.env.example](../.env.example) | README and operations |
| Native citation failure retained | [native-observation.json](../scripts/evaluation/native-observation.json) | Index evaluation and known limitations |

This source review and local startup do not re-run the entire v2.5 validation or
certify another host. Future filtering, diagrams, AI providers and memory remain outside v2.6.

A separate read-only agent review started from README without previous project context
and found analysis, security, setup, limitations and history within approximately one
minute. It rechecked the archive index and technical guards after corrections. This
is navigation evidence from an agent-assisted review, not independent human approval.
