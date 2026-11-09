# SpecHelper

SpecHelper is a self-hosted application for exploring software projects with AI
and turning a business need into a ticket and a `goal.md` for a coding
agent. It is intended for business users, analysts and developers working with a
trusted team, across different applications and technology stacks.

Start in **Analyses** with one conversational assistant. Ask about the existing
code, add documents and clarify the need. Choose **Deep analysis**, review or edit
the need in a centered modal, and confirm the launch. SpecHelper selects relevant
context with the conversational session, then runs an Analyst, an independent Counter-analyst and a Validator in
separate sessions. Results retain sources, frozen Git references and unresolved
limits. A conversation stays open after a response or a result: it can contain
several independent deep analyses and several tickets. Archive conversations to
keep the active list short without losing their history. The French interface
calls the final role **Validateur**.

## What you can do

- Continue discussions through native Codex, Claude Code or Antigravity sessions
  when the provider can resume them; recover explicitly when a session is lost.
- Keep the recorded AI/model history and explicitly choose another available
  connection if the selected assistant has exhausted its quota.
- Read authorized Git repositories, attachments and environment reference documents.
- Search repositories, branches and tags across paginated source listings, with
  separate branch/tag choices and preservation of the current selection.
- Check environment branches for available updates and update one repository or
  the whole environment without changing earlier analyses' frozen references.
- Optionally inspect a business PostgreSQL database through restricted read-only access.
- Follow observed work, answer clarifications and inspect a concise result or detailed report.
- Delete one deep-analysis cycle while preserving the conversation, other cycles
  and tickets. Remove a publication from SpecHelper without deleting its external ticket.
- Prepare a ticket directly in a centered modal using the conversational assistant.
  Keep one active draft per conversation and review AI updates before applying them. Reuse
  existing findings, keep later proposals explicitly unverified and choose whether
  to update the analysis. Publish conversation drafts, with or without deep analysis,
  to GitHub Issues, GitLab
  Issues, Jira Cloud or GLPI after an explicit confirmation, acknowledging any missing
  independent verification. Published links stay in the conversation. Reports, original
  files and `goal.md` are optional deliverables.

SpecHelper does not modify source code or business databases. Independent checks
help expose uncertainty; they do not guarantee that every AI conclusion is correct.
Four built-in skills support source exploration, documents, impact analysis and data
protection. Responses adapt to the question: functional explanations by default,
with code, Git history or authorized data when explicitly requested.

The [stabilization review](docs/stabilization.md) distinguishes tested guarantees,
release blockers and the real-world acceptance journey still required before a
stable release.
See [local operations](docs/local-administration.md) for safe stop/clean/purge commands and
load-test methodology, and the [latest qualification results](docs/stabilization-follow-up.md)
for executed measurements and remaining limits.

## Quick start

You need Docker Engine on Linux or Docker Desktop, Docker Compose supporting
`!reset`, and working Linux namespaces for the isolated agent runtime.

From a checkout of this repository:

```sh
cp .env.example .env
```

Choose a private `POSTGRES_PASSWORD` in `.env`, then run:

```sh
docker compose up --build -d
docker compose ps
```

Open <http://localhost:3000>, or enable [HTTPS with Caddy](docs/https.md) for
`https://localhost` or your own domain. Select **Administration** at the bottom left:

1. Under **Environments → Manage Git connections**, connect GitHub or GitLab.
2. Under **AI & Agents → Connections**, connect an eligible AI account and select
   its model. Use **Orchestration** to check coverage of all three analysis roles.
3. Under **Environments**, select repositories and branches/tags, optionally add a
   read-only PostgreSQL connection and reference documents, then update the environment.
4. Open **Analyses → New analysis**, select the environment and describe your need.
   Start the discussion; launch deep analysis when you want independent verification.

An eligible provider account and authorized source access are required for real
AI work. Ticket publication and business PostgreSQL access are optional. The
interface and generated deliverables support English and French.

## Team access and practical limits

Remote deployment requires shared instance authentication and HTTPS. Analyses,
conversation history and activity are shared across authorized browsers of the instance.
There are no individual human accounts or organization tenants. Each conversation
keeps its own AI session, independently of the browser used to open it. Read
[SECURITY.md](SECURITY.md) before exposing an instance or sending sensitive data.

Several conversations can use one account simultaneously: the default ceilings
are four active AI invocations per detected account and two across the instance.
The reference runtime also admits two invocations; additional conversations queue.
Each conversation keeps one active operation. Provider quotas, account restrictions
and host resources still apply; aliases of an account share its budget. See
[concurrent work](docs/installation.md#concurrent-work) before changing these limits.

Partial results remain visibly qualified. Publishing a draft without complete
independent verification requires an additional explicit acknowledgement.
Configuration or a model catalogue does not prove subscription access. Live model
accuracy, cost and throughput are not certified by application tests.

## Documentation

- [Installation](docs/installation.md): deployment, verification, upgrades and backups
- [Configuration](docs/configuration.md): AI accounts, environments, skills and connectors
- [Usage](docs/usage.md): conversations, deep analysis, results and ticket publication
- [Architecture](docs/architecture.md): services, isolation, sessions and concurrency
- [Development](docs/development.md): local setup, tests and evaluation tools
- [Local administration](docs/local-administration.md): safe stop, clean, purge and load probes
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md)

## License

SpecHelper-owned code and documentation use the [MIT License](LICENSE).
Dependencies, bundled tools and provider services retain their own terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Built containers are not exclusively MIT-licensed.
