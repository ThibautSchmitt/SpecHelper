> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# v1.8 interface acceptance — October 22, 2026

## Functional coverage

| Requirement | Implemented behavior | Evidence |
|---|---|---|
| FR-01–03: consistent navigation and layout | Fixed Requests/Questions/Tickets/Settings sidebar, central content, shared task panel, restrained cards and spacing, connection/admin footer | Four-page light/dark desktop/mobile rendered review; navigation regression tests |
| FR-04: desktop queue | Persistent desktop column; accessible small-screen drawer | Shell tests, rendered review and deployed checks |
| FR-05: task details | Title, identifier, status, actual assistant and role, current stage or pause/error reason; truthful non-AI executors | Queue API tests and browser cases |
| FR-06–08: dynamic order and motion | Running group first, waiting/clarification/completed/error groups, measured 250 ms position transitions, reduced-motion support | Controlled live status transitions and browser animation inspection |
| FR-09–10: Requests | No comparison checkbox; environment, persisted type, description, file drop zone and submission; searchable/filterable existing items | Creation policy tests, form/browser scenarios and real API-backed fixture workflow |
| FR-11–12: Questions | No comparison checkbox; persisted question type, answer overview and full explanation; follow-up/copy/documentation/request actions below answer | Question API/flow regression tests, browser version/copy/handoff and rendered preview |
| FR-13–14: Settings policy | Git, named assistants/models, environments, roles/skills and appearance; independent comparison selected by server configuration | Creation/role policy tests and Settings browser scenarios |
| FR-15–17: themes | Light/Dark/System with identical hierarchy, browser persistence, cross-tab storage updates and live system preference handling | Theme browser scenarios, source review and rendered palette checks |

## Non-functional coverage

| Requirement | Evidence |
|---|---|
| NFR-01: readable business interface | Compact functional headers, explicit type choices, progressive connection editors and existing language localization; no fabricated application-user identity |
| NFR-02: restrained motion | Position animation lasts 250 ms, affects orientation only and is disabled for reduced motion |
| NFR-03: status readability | Text labels plus blue/orange/muted amber/green/red semantic tokens in both palettes; sampled rendered text contrast checks meet 4.5:1 |
| NFR-04: scan the queue without opening detail | State groups, identifiers, current/previous assistant distinction, stage and waiting/error reason are visible on cards |

The reference layout is reflected through the shared shell, form/type/drop-zone
arrangement, item lists, question summary/key points/references, ticket table with
selected detail, and settings/appearance grouping. Written behavior takes precedence
where illustrative images retain an obsolete checkbox. Existing attachment limits
and safeguards are preserved rather than replaced with illustrative limits.

## Policy, data and security

Comparison is computed at creation from the instance policy and enabled,
authenticated configurations with a counter-analyst role. One connected account
can provide independent sessions. Legacy form flags cannot override this policy;
temporary capacity does not silently downgrade it. Existing items keep their
recorded comparison choice. Categories are included in the analysis dossier and
new frozen run manifests; earlier results and snapshots are not rewritten.

Migration 0020 adds categories and assigns General to historical questions. A
protected PostgreSQL backup was restored into a disposable database before the
upgrade. All **sixteen checked historical model fingerprints** match before and
after both the restored and deployed migration, excluding only the new category
field. The preexisting queued analysis was retained, and the worker was restarted
after the deployed fingerprint check.

Themes are browser preferences, not an authentication boundary. The sidebar
administration shortcut identifies the existing shared workspace without inventing
an application account. Ticket details display the stored publication payload,
labels and provenance. Refresh reads local records and does not pretend to retrieve
live tracker state or trigger remote updates. External publication remains an
explicitly confirmed operation through existing connectors.

Git/source/attachment isolation, read-only business database access, credential
handling and immutable version boundaries remain unchanged.

## Verification

- Backend: **421 passed, one skipped**, on disposable PostgreSQL 17 including business-database integration. The skipped host test requires Linux.
- Frontend production build, TypeScript, Ruff, migration consistency and Compose configuration pass.
- Complete Python and TypeScript Linux question-to-request workflows pass from the built runtime image, including independent Codex/Claude terminal stand-ins, clarification, two answer versions, three documentation formats and current-source reinspection.
- These deterministic workflows exercise application integration and Bubblewrap, not real-model quality. The existing connected-account quota limit was not reset.

- Browser regression suite: **110 desktop/mobile scenarios passed**, including English/French, versioned explanations, attachments, real isolated API-backed fixtures, task transitions, ticket details and all three theme preferences.
- Four additional visual scenarios cover all four main pages in both palettes at 1440×1000 and 390×844. They verify navigation, focus, containment and sampled 4.5:1 text contrast. Screenshots are retained locally and reviewed against the reference layout.
- Changed connection labels and queue wrapping are rechecked through targeted browser scenarios after final polish.

Two additional desktop/mobile checks pass against the deployed production build
and actual application API. They visit all four pages, exercise Light/Dark/System
including reload and device changes, verify Tab focus and queue-drawer dismissal,
and observe no API writes or page errors. Synthetic analysis results remain
exclusively in isolated development fixtures.
