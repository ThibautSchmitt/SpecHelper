# Security

SpecHelper is designed for a trusted team. An instance shares requests and connections and provides no application accounts or private spaces. Protect remote access through team infrastructure; do not expose Admin directly.

## Deployment

The default deployment publishes only the frontend on `127.0.0.1:3000`. Neither
the API nor the agent runtime exposes a host port. For remote access, protect the
entire instance, including Admin, with your team's VPN, reverse proxy or SSO,
serve it over HTTPS, and configure `BIND_ADDRESS`, `TRUSTED_ORIGINS` and
`ALLOWED_HOSTS` for the deployment.

Source workspaces and attachments are mounted read-only in the agent sandbox.
Analyzed PostgreSQL databases require dedicated read-only roles. GitHub and
database credentials are not added to AI prompts. Attachments remain untrusted
data and must never be executed as instructions.

The Linux sandbox requires specific namespace capabilities and network boundaries.
Preserve those boundaries when adapting deployment; see
[implementation notes](docs/implementation.md#services-and-runtime).
See [operations](docs/implementation.md#operations) for coordinated backups and
persistent volumes.

## Reporting a vulnerability

Do not disclose vulnerabilities containing secrets or real data in a public issue. Once the GitHub repository exists, use **Report a vulnerability** if private reporting is enabled. Otherwise, ask the maintainer for a private channel without disclosing exploit details. No temporary personal contact is listed before the GitHub account is selected.

A useful report includes the version, minimal reproduction, impact and prerequisites, using fictional data. Never send AI, GitHub or database credentials or private team attachments.
