# v1.3 acceptance report

Verification date: 2026-10-22.

## Delivered behavior

- Desktop layout has a persistent instance sidebar, central page and shared task
  queue. Requests, Tickets and Settings are the three navigation entries. Mobile
  keeps navigation accessible and opens the queue in a keyboard-accessible drawer.
- Connection indicators use backend observations. Queue cards expose real state,
  FIFO positions, elapsed processing time and linked objects. Clarification releases
  the worker; terminal history is bounded. Repositioning respects reduced motion.
- Settings supports encrypted, masked GitHub, GitLab, Jira and GLPI publication
  connectors, connection testing and allowed destinations. Agents cannot publish.
- A result version opens an explicit publication dialog. Destination metadata,
  templates, required fields, defaults and permissions constrain editable content.
  Preview precedes human confirmation. Changed metadata requires another review.
- Publications retain their immutable source version and edited payload. Persistent
  operation identifiers, destination uniqueness and reconciliation prevent blind
  retries after ambiguous writes. Definitively rejected attempts remain recorded;
  corrected content can be reviewed and submitted separately.
- Tickets lists confirmed publications with destination, external identifier, link,
  timestamp, source request/version, platform/environment filters and pagination.
- Existing analysis, clarification, comparison, continuation, exports, immutable
  baselines, read-only boundaries and English/French behavior remain available.
  The application adds no code-writing, branch, commit or pull-request action.

## Evidence

- Backend: 229 tests pass on disposable PostgreSQL 17. Coverage includes provider
  contracts, encrypted credentials, mandatory fields, target/template changes,
  concurrent attempts, malformed provider responses, uncertain writes, queue views
  and migration preservation.
- Browser: 42 desktop/mobile scenarios pass, including both languages, shared
  queue updates, publication recovery, historical versions and delayed settings
  responses. A separate read-only check passes against the deployed application
  on desktop and mobile, including existing results and the publication dialog.
- A real loopback HTTP integration exercises creation and response loss after
  acceptance against a controlled GitLab-compatible server. Recovery finds the
  accepted issue without a second creation request. This is a contract fixture,
  not a live GitLab service.
- GLPI 11.0.7 was installed in disposable local containers with MariaDB 11.4.
  The actual legacy REST API passed authentication, entity/category discovery,
  template discovery, required/hidden/read-only fields, predefined values,
  severity configuration, ticket creation and reference-based reconciliation.
  Reading back the ticket confirmed its template, category and field values.
  This exposed and fixed numeric configuration values returned as strings.
- Production frontend build, TypeScript, Ruff, migration consistency and Compose
  validation pass. Linux runtime isolation and deterministic Codex comparison and
  Claude continuation smoke checks pass; these do not measure model quality.
- A restored application database migrated successfully. All nine historical data
  fingerprints matched before and after the deployed migration. Existing
  connections, requests, conversations, result versions and artifacts were retained.

## Compatibility and limits

GitHub.com Issues, GitLab REST v4, Jira Cloud REST v3 and GLPI legacy REST v1 are
supported. See [connector behavior](ticketing.md) for field/template restrictions
and native-form fallbacks. GLPI 11.0.7 has actual vendor-service evidence; other
GLPI versions require instance-specific verification. Jira Data Center is not
claimed as compatible.

GitHub, GitLab and Jira adapter behavior was verified with deterministic API
contracts; no ticket was created in a team account during this review. A successful
connection test does not prove publication permissions for every destination.
Actual account publication requires a user-reviewed destination and explicit
confirmation in the application. No provider-wide compatibility claim is made.

The instance remains shared infrastructure without application user accounts or
private user spaces. Infrastructure authentication is required for remote access.
