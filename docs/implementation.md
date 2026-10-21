> Public version: session/request identifiers and instance references are anonymized. Original evidence remains local. Working PDF briefs are not distributed in this repository.

> Historical v1.0 implementation notes. Current behavior, migrations and evidence are documented in the [v1.2 audit](acceptance-v1.2.md), [v1.1 audit](acceptance-v1.1.md) and README.

# v1.0 specification tracking

Source: `SpecHelper_Cahier_des_charges_v1_0.pdf` (29 sections).

This document tracks the full scope. A requirement is accepted only after verification. The [detailed audit](acceptance.md) distinguishes every section, thirteen criteria and outstanding evidence.

| Requirement | Expected implementation | Expected evidence |
|---|---|---|
| 1, 6, 28.1 | GitHub connection, organizations, repositories, branches | Controlled GitHub transport API and integration test |
| 5, 28.2, 28.13 | Name/color, shadcn/Tailwind tokens | API persistence and browser checks |
| 7, 19, 28.6 | ChatGPT/Claude, persistent credentials, per-request sessions and resume | Isolated runtime and clarification/resumption scenario |
| 8, 28.4, 28.8–9 | Optional database, read-only role/transactions | Actual PostgreSQL: reject privileged roles and writes |
| 9–12, 28.3 | Multiple environments, shared mirror/worktrees, sync/health check | Real Git with two branches |
| 13, 28.12 | Immutable baseline and workspace | Synchronize after analysis without changing the snapshot |
| 14–15, 28.5 | Business workflow, isolated attachments | Browser and upload/path traversal tests |
| 16–20, 26 | Persistent queue, clarification, analysis and states | Worker tests and browser workflow |
| 17, 27, 28.9 | Read-only sources, secrets outside prompts, no database writes | Isolation tests inside Docker runtime |
| 21, 28.11 | Fast acknowledgment, progress, interruption before 300 s | Timeout test and integration timings |
| 22–23, 28.10 | Complete ticket, Jira copy, Markdown download | Schema, export and browser validation |
| 24–25 | Required stack, Compose/volumes, ten models | Build, migrations, Compose startup |
| 2–4 | Trusted team, no accounts, Admin panel, system | Interface and deployment documentation |

An administrator configures real GitHub/AI accounts. Deterministic tests use controlled transports and a test agent; they do not establish a real model's analysis quality.

## Checks performed on October 20, 2026

- 62 backend tests passed with Django using actual PostgreSQL 17 in a disposable container. `backend/tests/test_admin.py` covers encrypted GitHub credentials, discovery and pagination. `test_git.py` uses real Git, two branches and one mirror; resynchronization preserves request workspace and SHAs. `test_postgres_integration.py` verifies read-only roles/transactions and rejection of superusers, table writes and column writes.
- `test_workflow.py` covers isolated uploads, executable rejection, baselines, answers, session identity, export and 295-second supervision. `test_runtime.py` covers internal authentication, workspace path confinement, explicit session resumption, agent termination and database capability expiration.
- Ten Playwright desktop/mobile scenarios passed: administration, business workflow and connections. They include an 11 MB attachment, clarification, answer, ticket, Jira copy and Markdown download, with no horizontal overflow. AI results are explicit fixtures; no model is called.
- Production Next.js build, TypeScript, Ruff, migrations and Compose validation passed. Frontend, backend, worker and runtime images built.
- `python -m runtime.smoke` with Compose capabilities: reads of sources/Git history/attachments; rejected writes to source, cache and attachment; secrets and other sessions inaccessible; own session writable.
- `python -m runtime.workflow_smoke codex` and `claude`: full API/worker/CLI workflow using a real local repository and Bubblewrap, clarification, same-session resumption and SHA export. Latest acknowledgments: 0.167/0.171 s; deterministic workflows: 0.481/0.497 s. These are not real-model benchmarks.
- Docker network: runtime-to-backend connection on the application network rejected; worker reaches runtime through the control network.
- Installed binaries: Codex CLI 0.163.0 and Claude Code 2.1.116. Without credentials, connection status is DISCONNECTED and quotas UNKNOWN.
- All five Compose services started. Health endpoint: `http://localhost:3000/api/health`. Both desktop/mobile Admin scenarios also passed against the production build and PostgreSQL. Test name/theme restored afterward. Only frontend port 3000 is published on 127.0.0.1.
- Token-free connections: guided GitHub/ChatGPT/Claude dialogs, temporary code or Claude confirmation, progress and cancellation. Six browser scenarios use controlled responses. A disposable Compose deployment started the three real CLIs through the public API, received official authorization links on github.com, auth.openai.com and claude.com, then canceled each attempt.
- Worker control relay is authenticated and restricted to connection/health operations. Internal secrets are generated in protected volumes outside the sandbox. Tests cover the relay, concurrent secret generation and credential renewal without overwriting a newer login.

## External validation limits

The user connected GitHub and ChatGPT. Discovery, a public project and both private projects in the existing environment were synchronized with those accounts. Real analyses with/without attachments produced tickets after clarification and session resumption; sources, sections, exports and timings are checked in the [detailed audit](acceptance.md).

Final post-answer jobs took 45.786 and 73.546 s. First clarification took 23–26 s, exceeding the indicative 15-second ideal. Simple/standard targets and the mandatory five-minute limit are distinct. These results do not guarantee external-provider latency. A reduced-budget real Linux timeout supplemented the 295-second supervisor tests.

Claude remains an alternative. Its official authorization startup and adapter were tested; no analysis using a real Claude account is claimed. The specification requires at least one of the two terminal agents; connected analyses above used Codex.
