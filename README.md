# SpecHelper

SpecHelper is a self-hosted application that turns a business request into:

- a concise ticket ready to copy into Jira;
- a detailed `goal.md` that can be given to a coding agent.

It analyzes requests against actual project sources, configured Git environments,
optional PostgreSQL databases and user-provided attachments. One instance serves
a trusted team with shared GitHub, ChatGPT and/or Claude connections.

## Features

- Multiple GitHub/GitLab sources, forks and environments with dedicated branches
- Optional read-only PostgreSQL connection per environment
- ChatGPT / Codex and Claude / Claude Code support
- Named assistant configurations, model selection and shared account availability
- Business clarification before technical analysis
- Optional environment instructions and versioned reference documents
- Screenshots and document attachments
- Optional comparison of independent AI analyses, with one or two connected assistants
- Configurable analyst/counter-analyst roles and optional independent verification
- Concise tickets and detailed `goal.md` files
- Continued discussion with immutable, versioned results
- Persistent request queue
- English and French interface and generated content
- Human-confirmed publication to GitHub Issues, GitLab Issues, Jira and GLPI

SpecHelper does **not** modify source code, create pull requests or write to
analyzed business databases.

## Installation

Use Docker Engine on Linux or Docker Desktop on macOS/Windows, with Docker Compose
and Linux namespace support for the agent runtime.

```sh
cp .env.example .env
# Configure the application database password in .env.
docker compose up --build -d
```

Open <http://localhost:3000>.

SpecHelper has no application-level user accounts or private user spaces. For
remote access, protect the entire instance with your VPN, reverse proxy or SSO
and serve it over HTTPS. See [deployment and security](SECURITY.md).

## Configuration

Open **Settings** after starting the application. Labels follow the selected language.

1. **Connect Git sources.** Add named GitHub or GitLab connections under
   **Sources Git**. GitHub supports browser authorization; GitLab accepts a
   read-only token for GitLab.com or a self-hosted instance.
2. **Connect an AI assistant.** Connect ChatGPT / Codex, Claude / Claude Code, or
   both through the official authorization dialogs. Add named configurations,
   choose models and optionally share an account identity. A compatible provider
   subscription may be required. No personal access token or terminal command is
   needed in SpecHelper. An available assistant is selected automatically.
3. **Create an environment.** Select repositories and their branches, then wait
   for synchronization. Each environment can combine several repositories and an
   optional PostgreSQL connection. Repositories and branches can later be changed
   or synchronized from Settings.
4. **Optionally connect PostgreSQL.** Use a dedicated read-only account. **Test
   connection** verifies connectivity, a read query and read-only access. Database
   credentials are never included in AI prompts.
5. **Set up the instance.** Choose the team name, optional short label, color,
   application language and whether comparison is available for new requests.
   The language applies to the interface and new analyses; existing requests keep
   their language and published files. See [English and French](docs/localization.md).
6. **Optionally set up ticket publication.** Add and test a ticket connector, then
   select its allowed destinations. See [publishing tickets](docs/ticketing.md) for
   supported API versions, credentials and template behavior.

Optional [environment context](docs/environment-context.md) adds short project instructions
and reference documents. Existing analyses retain their original document versions.

## Usage

From **Requests**:

1. Select an environment.
2. Describe the business need.
3. Attach screenshots or documents if useful.
4. Optionally enable **Compare multiple analyses**.
5. Start the analysis and answer any clarification questions.

The sidebar provides **Requests**, **Tickets** and **Settings**. A shared task queue
stays visible on desktop and is available in a drawer on smaller screens.

The result includes two downloadable files:

- **Ticket:** context, requested behavior, proposed solution, technical impact,
  risks and acceptance criteria, ready to copy into Jira.
- **`goal.md`:** business intent, Git baseline, relevant files and symbols,
  implementation constraints, acceptance criteria and expected tests for a coding agent.

Use **Continue discussion** to refine a result. Each new result is stored as a
separate immutable version; previous versions remain available. SpecHelper does
not create external tickets automatically. Use **Publish ticket** to review the
target, fields and preview, then explicitly confirm creation. Published tickets
remain linked to the exact result version under **Tickets**.

## Architecture

Docker Compose runs five services:

```text
frontend
backend
worker
database
agent-runtime
```

The stack uses Next.js / React / TypeScript, shadcn/ui, Tailwind CSS, Django /
Django Ninja, PostgreSQL, Codex CLI and Claude Code.

AI agents operate inside an isolated Linux runtime with read-only access to
project sources and request attachments. The default worker processes queued
requests sequentially.

See [architecture and implementation notes](docs/implementation.md) for sandboxing,
networking, worktrees, PostgreSQL capabilities, orchestration and operations.

## Security

SpecHelper is intended for trusted team infrastructure. Analyzed source workspaces
and business database access are read-only. GitHub and database credentials are
not added to prompts, attachments are isolated by request, and AI execution is sandboxed.

Read [SECURITY.md](SECURITY.md) before exposing an instance outside a local environment.
Application access must be protected by infrastructure-level authentication.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, tests and linting.

Further documentation:

- [Functional specification](docs/specification.md)
- [Environment context](docs/environment-context.md)
- [v1.6 acceptance report](docs/acceptance-v1.6.md)
- [Implementation, operations and runtime checks](docs/implementation.md)
- [English and French](docs/localization.md)
- [Ticket publication and connectors](docs/ticketing.md)
- [Git sources, AI configurations and availability](docs/connections.md)
- [Analysis roles and verification](docs/orchestration.md)
- [v1.5 acceptance report](docs/acceptance-v1.5.md)

## License

SpecHelper-owned code is released under the [MIT License](LICENSE).
Third-party dependencies retain their respective licenses and notices; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Built images are not exclusively MIT-licensed.
