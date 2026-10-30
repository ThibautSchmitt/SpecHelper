# SpecHelper

SpecHelper is a self-hosted application for exploring software projects with AI
and turning a reviewed business need into a ticket and a `goal.md` for a coding
agent. It is intended for business users, analysts and developers working with a
trusted team, across different applications and technology stacks.

Start in **Analyses** with one conversational assistant. Ask about the existing
code, add documents and clarify the need. When you choose **Launch deep analysis**,
SpecHelper runs an Analyst, an independent Counter-analyst and a Verifier in
separate sessions. Results retain sources, frozen Git references and unresolved
limits. The French interface calls the final role **Validateur**.

## What you can do

- Continue discussions through native Codex, Claude Code or Antigravity sessions
  when the provider can resume them; recover explicitly when a session is lost.
- Read authorized Git repositories, attachments and environment reference documents.
- Optionally inspect a business PostgreSQL database through restricted read-only access.
- Follow observed work, answer clarifications and inspect a concise result or detailed report.
- Prepare and edit tickets for GitHub Issues, GitLab Issues, Jira Cloud or GLPI,
  then explicitly confirm publication. Reports, original files and `goal.md` are optional deliverables.

SpecHelper does not modify source code or business databases. Independent checks
help expose uncertainty; they do not guarantee that every AI conclusion is correct.

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

Open <http://localhost:3000>. Select **Administration** at the bottom left:

1. Under **Environments → Manage Git connections**, connect GitHub or GitLab.
2. Under **AI & Agents → Connections**, connect an eligible AI account and select
   its model. Use **Orchestration** to check coverage of all three analysis roles.
3. Under **Environments**, select repositories and branches/tags, optionally add a
   read-only PostgreSQL connection and reference documents, then synchronize.
4. Open **Analyses → New analysis**, select the environment and describe your need.
   Start the discussion; launch deep analysis when you want independent verification.

An eligible provider account and authorized source access are required for real
AI work. Ticket publication and business PostgreSQL access are optional. The
interface and generated deliverables support English and French.

## Team access and practical limits

Remote deployment requires shared instance authentication and HTTPS. New
conversations are isolated by a signed browser-owner cookie; older shared analyses
remain shared. There are no individual human accounts or organization tenants.
Keep the original browser profile to reopen its private conversations. Read
[SECURITY.md](SECURITY.md) before exposing an instance or sending sensitive data.

Several conversations can use one account simultaneously: the default ceilings
are four active AI invocations per detected account and eight across the instance.
Each conversation keeps one active operation. Provider quotas, account restrictions
and host resources still apply; aliases of an account share its budget.

Partial results remain visibly qualified and cannot publish a new external ticket.
Configuration or a model catalogue does not prove subscription access. Live model
accuracy, cost and throughput are not certified by application tests.

## Documentation

- [Installation](docs/installation.md): deployment, verification, upgrades and backups
- [Configuration](docs/configuration.md): AI accounts, environments, skills and connectors
- [Usage](docs/usage.md): conversations, deep analysis, results and ticket publication
- [Architecture](docs/architecture.md): services, isolation, sessions and concurrency
- [Development](docs/development.md): local setup, tests and evaluation tools
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md)

## License

SpecHelper-owned code and documentation use the [MIT License](LICENSE).
Dependencies, bundled tools and provider services retain their own terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Built containers are not exclusively MIT-licensed.
