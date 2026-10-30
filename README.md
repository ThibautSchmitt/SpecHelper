# SpecHelper

SpecHelper helps a trusted team understand an existing application and turn a
business need into an actionable ticket and a detailed `goal.md` for a coding agent.

One conversation starts with a single persistent assistant. **Launch deep analysis**
explicitly runs independent analysis, counter-analysis and validation of actual sources.
Optional read-only PostgreSQL investigations
and official external references add evidence where relevant. Questions explain existing
behavior with sources; Requests describe a desired change.

Results keep their Git baseline, evidence and unresolved limits. People review
business decisions and explicitly confirm publication to a ticket platform.
SpecHelper does not implement source changes or write to analyzed business databases.

## Quick start

Requirements: Docker Engine on Linux or Docker Desktop on macOS/Windows, a current
Docker Compose supporting `!reset`, and working Linux namespaces for the agent runtime.

From the repository root:

```sh
cp .env.example .env
```

Set `POSTGRES_PASSWORD` in `.env` to a password of your choice, then start:

```sh
docker compose up --build -d
```

Open <http://localhost:3000>. In **Settings** at the bottom left:

1. Connect GitHub or GitLab.
2. Connect ChatGPT / Codex or Claude / Claude Code using guided authorization,
   or sign in to [Antigravity](docs/antigravity.md) with your Google account.
3. Create an environment with repositories and branches, then wait for synchronization.
4. From **Analyses → New analysis**, select an environment and describe a question, a change or both,
   with optional files. Resume the work from **Analyses**.
5. Discuss freely, then choose **Launch deep analysis** when independent verification
   is needed. Reports and reviewed ticket preparation follow its result.

See the [conversation workflow](docs/analysis.md#one-conversation-two-phases) and
[provider validation and limits](docs/conversation-validation.md).

An eligible provider account/subscription and repository access are needed for real
analyses. PostgreSQL and ticket publication are optional. The interface and generated
files support English and French.

Results retain their discussion and dated need revisions. A sourced answer can lead
to a linked change. Useful explanatory diagrams retain reviewed relationships and
exportable Mermaid sources; simple questions do not require a diagram.

Startup was checked with fresh application volumes; see the
[installation observation](docs/operations.md#installation-observation) for its scope
and [operations](docs/operations.md#installation-settings) if port 3000 is occupied.

## Use with your team

One self-hosted instance shares requests, results and connections with a trusted team.
There are no individual user accounts or private spaces. The default bind is localhost;
remote access requires configured shared authentication and HTTPS.
Read [SECURITY.md](SECURITY.md) before exposing an instance. Project excerpts,
documents and permitted database observations may reach your configured AI provider.

Independent review and source checks help expose uncertainty; they do not certify every
AI conclusion. Read the [known limitations](docs/known-limitations.md).

## Documentation

- [Product overview](docs/overview.md): outputs and the Request/Question workflow
- [Configuration](docs/configuration.md): connections, environments and settings
- [Analysis](docs/analysis.md): clarification, independent review, evidence and results
- [Ticket publication](docs/ticketing.md): reviewed drafts, templates and delivery
- [Architecture](docs/architecture.md) and [operations](docs/operations.md)
- [Contributing](CONTRIBUTING.md): development, checks and documentation maintenance
- [Changelog](CHANGELOG.md), [historical evidence](docs/archive/README.md) and [future scope](docs/roadmap.md)

## License

SpecHelper-owned code is released under the [MIT License](LICENSE). Dependencies
retain their licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
Built images are not exclusively MIT-licensed.
