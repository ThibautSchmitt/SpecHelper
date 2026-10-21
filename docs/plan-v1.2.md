> Public version: session/request identifiers and instance references are anonymized. Original evidence remains local. Working PDF briefs are not distributed in this repository.

# v1.2 delivery

Reference: SpecHelper_Cahier_des_charges_v1_2.pdf (11 pages, 18 sections, FR-01 through FR-17 and ten criteria).

- Preserve the shared team instance without accounts, simple queue, Git/worktrees/baselines, Linux isolation, request-specific files, immutable versions and discussion.
- AI connections: independent Codex and Claude connections, availability separate from authentication, automatic selection, exclusion of known exhausted quotas, bounded fallback and queueing when nothing can start. Never invent remaining quotas.
- Comparison: optional business-facing checkbox; two analyses in independent sessions/directories, two providers when available or two sessions of one provider. Structured synthesis in a third context; no open-ended debate.
- Resumption: preserve contexts when their provider is available; store multiple sessions per request and never send a session ID to a different provider.
- Compact Admin: Connections, Environments, Instance. At the user's request, no agent/skill tab or settings, including advanced options. These mechanisms remain internal.
- PostgreSQL: host or URL form; one test checks connectivity, SELECT 1 and read-only rights. Only three simple statuses, masked secrets, no schema/version diagnostics.
- Outputs: context of 1–3 sentences, separate need and expected behavior, concise ticket; detailed v1.2 goal with baseline, files/symbols, constraints, criteria and tests. Copy both artifacts and retain older versions.
- Internal configuration: enabled flags for profiles/skills; business and safety contracts remain mandatory. No role/skill configuration in Admin, advanced priorities, fairness or scheduler.
- Validation: API/queue/selection/quota/fallback, independent contexts and synthesis with one/two providers, actual PostgreSQL, Linux sandbox, migrations on an instance copy, desktop/mobile browser tests, connected-account tests and latency limitations.
- Deployment: back up the instance, preserve its environment/connections, wait for active jobs; audit FR-01–17 and criteria 1–10 before completion.

Initial state: deployed v1.1; singleton AIConnection and AISession OneToOne, one sequential worker.

Final state: deployed v1.2; models/migrations 0005–0006, independent connections, availability/quota/queue/fallback, three comparison contexts, v1.2 outputs and compact Admin. The advanced agent/skill block was also removed.

Tests: 89 passed with Django on PostgreSQL and a real disposable business-database DSN; 20 desktop/mobile browser scenarios, then eight v1.2 scenarios after the final removal. Production build and typecheck passed. Linux: normal Codex/Claude, single-Codex/single-Claude/dual-provider comparison and dual-provider comparison with PostgreSQL passed; deterministic CLIs verified isolation and read-only boundaries.

Connected validation: standard and single-Codex comparison with an attachment, then one continuation each; four READY results, same sessions, two immutable versions per request, jobs between 69.7 and 134.0 seconds excluding queue time. Copies/exports of both versions checked on desktop/mobile; older v1.1 result still usable. Claude disconnected: no claim of comparison using two real accounts.

Preservation: nine historical-data fingerprints identical before/after migration and after acceptance testing excluding the two validation requests. Existing environment unchanged, temporary environment deleted, mirror retained. Disposable PostgreSQL and development servers stopped; five Compose services remain available.

Full coverage and limitations: [acceptance-v1.2.md](acceptance-v1.2.md), sections 1–18, FR-01–17 and criteria 1–10. FR-10 follows the explicit product decision to keep agents/skills internal.
