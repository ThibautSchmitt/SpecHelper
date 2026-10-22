> Public version: session/request identifiers and instance references are anonymized. Original evidence remains local.

# v1.0 specification audit

This report covers v1.0 implementation and validation on October 20, 2026. Includes subsequent user requests for browser connections, no token entry and terminology accessible to business users.

“Verified” refers to the stated evidence scope. Deterministic agents validate orchestration software, not real-model quality or performance.

| Section | Requirements and evidence | Status |
|---|---|---|
| 1 | Consistent environment, business need, files, clarification, ticket: API, worker, workflow tests, Playwright and actual analysis | Verified |
| 2 | GitHub, primary assistant, environments, files, tickets; no accounts, multi-tenancy, code changes, PRs or business writes: models, routes, runtime, README reviewed | Verified |
| 3 | Five services/persistent volumes, infrastructure access control; Compose running with frontend only on localhost | Verified |
| 4 | Connections, Environments, Instance, System tabs; job states/log: interface and Playwright | Verified |
| 5 | Persistent name/color; shared CSS variables for header, buttons, badges, focus/navigation: shell.tsx, globals.css, browser theme test | Verified |
| 6 | Actual GitHub connection; paginated organizations/projects/branches; clone/fetch/SHA resolution; askpass credentials outside prompts: actual API, admin/Git tests, public environment synced | Verified |
| 7 | Actual ChatGPT connection; Claude alternative; persistent credentials, request-specific session/resume: auth.py, models, tests and actual analysis | ChatGPT verified; Claude tested without real account |
| 8 | Optional database; limited role, encrypted secrets, SELECT AST, read-only transaction/time/row limits: actual PostgreSQL 17 and database smoke | Verified |
| 9 | Multiple sources/optional database encapsulated by Environment; users select only environment: model/API/UI review | Verified |
| 10 | Name, multiple projects/versions, existing database or None; create/sync job: API/browser | Verified |
| 11 | One owner/project mirror, detached worktrees; two environments/two branches without extra clone: real Git test | Verified |
| 12 | Fetch, SHA resolution, materialization, Git/database checks, READY/ERROR; actual public synchronization | Verified |
| 13 | Frozen baseline/request workspace; later sync changes neither files nor exported SHAs: test_git.py | Verified |
| 14 | Environment, text and files; no Git/database choice in business form: desktop/mobile | Verified |
| 15 | Images/PDF/DOCX/text/allowed formats, isolated UUID paths, neutralized names, prompt references only, attachment downloads: upload/sandbox/browser tests | Verified |
| 16 | Persistent job, per-request session, terminal in immutable selected workspace snapshot: worker/runtime/workflow smoke/actual request | Verified |
| 17 | Analysis-only instructions, no commits/push/writes, pattern reuse, risks/uncertainty; read-only source/cache/file mounts and protected database | Verified |
| 18 | Understanding before exploration; NEEDS_CLARIFICATION or READY_TO_ANALYZE schema; stops on question: worker/tests/actual ChatGPT question and resumption | Verified |
| 19 | Persisted questions/answers, same terminal ID resumed: backend, both deterministic adapters and actual session through ticket | Verified |
| 20 | Git/log/show, rg, shell tools/files/attachments; optional database only through temporary capability: real sandbox/database smokes | Verified |
| 21 | Fast acknowledgment/progress; 295 s supervision, maximum 290 s agent budget; actual Linux interruption, fast acknowledgment, simple 45.786 s/standard 73.546 s after clarification | Safeguards verified; targets/limitations below |
| 22 | Complete business/technical sections, criteria, risks, tests, SHAs/attachments: schema/Markdown/export tests and actual ticket | Verified |
| 23 | Result, Jira copy/Markdown download, frozen references, prior questions: desktop/mobile Playwright | Verified |
| 24 | Next/React/TypeScript/shadcn/Tailwind, Django/Ninja, PostgreSQL/Git/Docker, Codex/Claude; builds/five-service startup | Verified |
| 25 | Ten specified models; Job/ConnectionAttempt persist execution/connections; migrations applied | Verified |
| 26 | DRAFT, QUEUED, UNDERSTANDING, NEEDS_CLARIFICATION, ANALYZING, GENERATING_TICKET, READY, PARTIAL, ERROR: models/worker/schema/UI | Verified |
| 27 | Trusted infrastructure, secrets outside prompts, protected volumes, network separation, read-only code/database, isolated files, no automatic attachment execution | Verified locally |
| 28 | Thirteen criteria below | Verified within stated scope |
| 29 | Frontend → API/worker → terminal session → sources/optional database/files → questions → ticket; no proprietary graph dependency | Inspection/integration verified |

| Criterion 28 | Evidence | Status |
|---|---|---|
| 1 | GitHub/ChatGPT connected through new buttons; actual discovery | Verified |
| 2 | Name/color persisted through API and checked in browser | Verified |
| 3 | Two environments/two branches in real Git, one mirror | Verified |
| 4 | Create without database, associate database, disposable PostgreSQL workflow | Verified |
| 5 | Browser workflow with environment, need, 11 MB file | Verified |
| 6 | Question/resume same ID; deterministic Codex/Claude and actual ChatGPT | Verified |
| 7 | Actual worktree/history read from Bubblewrap by ChatGPT; paths/behavior independently checked | Verified |
| 8 | Isolated agent → HTTP capability → actual PostgreSQL; no capability without database; expired access rejected | Verified |
| 9 | Source/cache/file writes denied by Linux; DELETE denied by API/PostgreSQL; unchanged source/table | Verified |
| 10 | Complete schema, reviewed real ticket, cited files exist, desktop/mobile export | Verified |
| 11 | 295 s supervisor/process termination; actual 0.123 s acknowledgment, standard 118.865 s | Actual scenario and termination tests verified |
| 12 | Frozen SHA export after later synchronization | Verified |
| 13 | Shared interface variables, desktop/mobile theme tests | Verified |

## Reproducible checks

- Final backend suite: 62 passed with **Django using PostgreSQL**, including business-database integration. SQLite also passed applicable tests before the final changes; changed workflow scenarios passed again. No-database startup covers FOR UPDATE OF restricted to Request, avoiding PostgreSQL errors on the optional join.
- Browser: ten scenarios passed; both business workflows rerun after adding immediate rejection when no assistant is connected. Fixtures stay in the dedicated local database and restore prior assistant state. This rejection describes historical v1.0 behavior, superseded by v1.2 capacity queueing.
- `runtime.smoke`: actual Linux isolation, reads and denied writes.
- `runtime.workflow_smoke codex` / `claude`: API/worker, actual Git/sandbox, deterministic CLI, clarification/resumption/export.
- `runtime.database_smoke codex` / `claude`: actual business PostgreSQL, reads from sandbox, denied writes, secrets outside prompts, capability expiration. Disposable server removed afterward.
- Both real CLIs launched with production options in a credential-free sandbox: Codex reached its provider and received HTTP 401; Claude returned “Not logged in.” This exercises startup/options without claiming a model response.

## Connected validation

Validation environment synchronized public project `public-validation-repository`, main, SHA `local-sha-removed`, without business database. Request `local-id-removed` used user-connected accounts and a text attachment, reaching READY with a complete ticket.

- Acknowledgment: **0.123 s**. First processing with clarification: **37.155 s**.
- After answer, understanding and analysis: **118.865 s**.
- Same session through ticket: `local-id-removed`.
- Actual attachment/source reads, git log/show/rg; cited files exist; Crontab::run() behavior independently checked. Correctly identified that the project manually launches tasks rather than supplying the external scheduler. No claim of having executed tests.
- Empty git status --porcelain; unchanged baseline.
- Actual desktop/mobile Chrome result: all sections/attachment, identical Jira copy/Markdown download, exact SHA, no overflow or JavaScript errors. Screenshots reviewed in `.local/screenshots/live-*.png`.

These trials exposed and fixed PostgreSQL locking on the optional join and nested-sandbox conflicts. Bubblewrap remains the effective read-only boundary; Codex's internal sandbox is disabled only inside it. Startup always begins with Bubblewrap and fails if isolation cannot start.

## Final version and measurements

The first help-text benchmark took **91.382 s**; phase-specific effort still took **89.170 s**. GPT-6-Luna completed it in **53.123 s**. These trials selected the faster model without reducing ticket sections. Superseded benchmark requests were cleaned up; reviewed results remain archived in `.local/`.

The final version adds a strict understanding schema preventing ticket generation before technical analysis and clarifies that Tests describes **expected future checks**. Two new connected requests verified it:

| Final scenario | Request | First clarification | Processing after answer | Result |
|---|---|---|---|---|
| Failure notification, with file | local-id-removed | 23.126 s | 73.546 s | READY, 13 ticket fields, five expected checks |
| Help text, without file | local-id-removed | 25.652 s | 45.786 s | READY, 13 ticket fields, three expected checks |

Both use distinct sessions resumed with the same IDs after answers. Cited sources exist and main behavior was independently checked. The first ticket correctly notes no scheduler or detached-mode supervision. The second preserves the existing example/language and limits scope to one help sentence. Repositories remain clean. The final notification ticket also passed desktop/mobile copy/download checks.

Acknowledgments remain below two seconds. Durations exclude human wait and distinguish processing from queue time. The 60 s simple and 180 s standard targets were met in these trials. **The ideal 15 s first clarification was not met in either trial.** This is observed latency, not a promised guarantee. The source describes this target as ideal, whereas exceeding five minutes explicitly requires interruption, protected by the 295 s supervisor and remaining agent budget.

An additional Linux trial launched a slow CLI in Bubblewrap with a one-second budget: stopped in **1.006 s**, process group removed and temporary capabilities cleaned. Production uses the same execution path; unit tests separately check the full 295 s supervisor. No benchmark guarantees all external-provider timings.

## User-configured environment

The existing environment is READY without a business database, with two user-selected projects on `validation-branch`. Actual synchronization took **216.614 s**. Earlier attempts hit a 90 s network budget; clone/fetch now allows ten minutes each, with a separate twenty-minute full-sync limit. Obsolete interrupted downloads were cleaned after success. Future sync errors are displayed distinctly from analysis errors.
