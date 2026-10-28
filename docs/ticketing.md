# Publishing tickets

Publication is a separate backend operation. Analysis agents cannot invoke it.
An explicit **Create ticket** confirmation is required for every publication.

## Set up a connector

In **Settings → Connectors**, find the relevant environment, add a named ticket
connector and test its connection. Each connector belongs to exactly one environment;
publication selects only destinations configured for the request's environment.
Select the accessible destinations allowed for publication and an optional default.
Credentials are encrypted, masked in the interface and excluded from analysis prompts.
Publication credentials must be distinct from repository-read credentials, including
when both accounts belong to the same person. Existing GitHub connectors that relied
on the shared source connection need a dedicated issue-publication token before
publishing again. Repository discovery and analysis continue independently.

| Platform | Supported connection |
|---|---|
| GitHub Issues | A dedicated github.com publication token restricted to allowed repositories and required issue permissions. |
| GitLab Issues | Cloud or self-hosted REST v4 endpoint and an access token with appropriate project issue permissions. |
| Jira | Jira Cloud REST v3, instance URL, account email and API token. |
| GLPI | Legacy REST v1 (`apirest.php`), enabled API access and a user token or username/password; application token when required. |

GitHub Enterprise, Jira Data Center and GLPI's newer API generation are not claimed
as supported by these adapters. A successful connection read does not guarantee
that the account can create tickets in every destination; write refusals remain errors.

The legacy API was exercised against a disposable GLPI 11.0.7 instance, including
template-driven creation and reconciliation. See the [v1.3 acceptance report](archive/reports/acceptance-v1.3.md)
for verification boundaries and the other platforms' contract-test coverage.

See [OAuth deployment options](provider-metadata.md#publication-oauth-options) for the
reviewed native browser flows and the current implementation boundary. Publication
OAuth is not configured or implemented by the current adapters; manual methods above
remain functional. Git source browser authorization is a separate read-only integration.

## Review and create

Open a result version and select **Prepare ticket**. Choose a configured connector
belonging to that environment and an allowed project. Choose **Project template**
or **Standard SpecHelper format**. Actual templates and issue types come from the
connector; multiple templates require an explicit choice. A matching analysis intent
may suggest a template, without restricting the user's choice. If no usable template
is exposed, the standard format is selected with an explanation. Required destination
fields still apply, including Jira issue types and custom fields.

The standard ticket contains a title, description, business summary, technical
summary and proposed solution. Critical restrictions remain visible. Detailed business
and technical sections are separate opt-in options. Changing presentation recomposes
the draft from immutable verified conclusions without invoking analytical agents;
the detailed `goal.md` and source evidence remain unchanged.

Draft options and human edits are persisted per analysis version, connector and project.
Reloading restores the draft; concurrent stale saves are rejected. Complete the target's
required fields and inspect the preview before confirming creation. The publication
snapshot retains the exact version, environment, Git baseline and reviewed fields.

Field mapping uses known ticket sections and preserves target defaults. Unknown
mandatory business information is left for the user. The server rechecks access,
allowed values and template revisions before sending. If the template changed,
review a fresh preview instead of sending the old payload.

GitHub and GitLab use Markdown. GitHub YAML form fields become Markdown sections.
Jira descriptions use ADF text paragraphs and GLPI descriptions use escaped HTML;
their preview shows literal text rather than promising Markdown formatting.
Filenames, code identifiers and source quotations remain unchanged.

## Attachments require explicit consent

**Include attachments** starts unchecked. Enabling it exposes a per-file selection,
with names, sizes, transfer availability and the destination. Original files and the
optional `goal.md` are distinct selections. No attachment is transferred while the
option is unchecked. A publication accepts at most 20 files and 50 MB in total;
each file must also satisfy its original safe-format inspection and 25 MB bound.
Selected bytes are checked against the preview's size, MIME and SHA-256 metadata.

Reviewed diagrams stay in the analysis report and `goal.md` by default. In standard
format, destinations supporting file uploads can receive an optional `diagrams.md`
annex. Enable **Include attachments**, then select that file explicitly. It contains
the Mermaid sources, alternative explanations and reviewed claim identifiers from
the chosen immutable version. Project templates and destinations without supported
uploads do not expose an enabled annex selection. The ticket body stays concise.

GitLab uses native project uploads and links them in a note on the created issue.
Jira uses native issue attachments, checking enabled status, upload size and the
connector's attachment permission before accepting a selection. GLPI legacy REST
uploads a Document and links it through Document_Item. Server-side permissions
remain authoritative and refusals are reported per file. The supported GitHub Issues
API does not expose an equivalent upload operation, so those files are visibly
unavailable for transfer; no undocumented upload endpoint is used.

Issue creation and file transfer have separate outcomes. A created issue remains
recorded if a file transfer fails or loses its response. The file is marked uncertain
and is never uploaded again automatically; inspect the destination before any manual
retry. A process interrupted before starting a selected transfer may resume that
unstarted transfer against the existing issue, without creating another issue.

## Platform templates

- **GitHub:** repository Markdown templates and YAML issue forms, including required
  fields, dropdowns, checkboxes and available defaults. Public account-level `.github`
  defaults are used when local templates/configuration do not override them.
  Unsupported field types fail explicitly. Unavailable default labels or assignees
  are reported for review rather than submitted as hidden invalid selections.
- **GitLab:** project issue templates exposed by the project templates API. Inherited
  templates depend on the server edition, API and account permissions.
- **Jira:** actual issue types and creation-field metadata. Unsupported required field
  types block publication; no file-template convention is assumed.
- **GLPI:** accessible entity/category metadata and legacy ticket-template rules.
  Supported required/default/hidden/read-only fields are validated against the
  accessible metadata. Unsupported or inaccessible mandatory business rules require
  the platform's native form. Automatic GLPI rules and server validation remain
  authoritative; unresolved rules are never silently treated as verified.

When no template is available, the default is the concise SpecHelper ticket.

## Results and uncertain delivery

A partial result can be inspected and prepared as a draft, but cannot create a new
external ticket. For current independent-analysis protocols, a READY label alone is
insufficient: completed Analyst, Counter-analyst and Verifier checks and non-blocking
verified claims are required. Missing checks and evidence limitations remain visible;
export or presentation changes cannot promote a partial analysis to verified.
Read-only reconciliation of an older publication remains available.
An edited need also blocks publication of earlier results until a new analysis
has reassessed it. Previously published external tickets are not rewritten.

**Tickets** lists confirmed publications with platform/environment/search filters,
their external identifier/link and the exact request/version that supplied the content.
Failed or uncertain attempts remain accessible from the request and queue.

A persistent operation key and destination constraint prevent duplicate creation
from double clicks, refreshes or concurrent browsers. A definitive rejection may
be corrected and submitted as a new reviewed attempt. Previous snapshots stay intact.

After a network interruption, **Verify existing publication** searches the target for
the original reference. An uncertain write is never retried blindly. Search indexing
or permissions can delay verification; a missing search result does not prove that
creation failed. Check the external platform when verification remains uncertain.

Connector endpoints with publication history cannot be retargeted; create a separate
connector for a different instance so recovery stays bound to the original service.

## API references

- [GitHub Issues](https://docs.github.com/en/rest/issues/issues#create-an-issue)
  and [issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)
- [GitLab project templates](https://docs.gitlab.com/api/project_templates/)
  and [issues](https://docs.gitlab.com/api/issues/), plus [Markdown uploads](https://docs.gitlab.com/api/project_markdown_uploads/)
- [Jira Cloud issue creation and metadata](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
  and [issue attachments](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-attachments/)
- [GLPI legacy REST API](https://github.com/glpi-project/glpi/blob/11.0/bugfixes/apirest.md)
  and [document upload contract](https://help.glpi-project.org/documentation/modules/configuration/general/api/api)

## Existing installation migration

The ownership migration keeps original connector rows and every publication link
and snapshot. Previously shared configurations are copied into each existing
environment, allowing subsequent changes to remain independent. With no environment,
legacy connectors remain saved under **Unassigned ticket connectors** until explicitly
assigned. A connector cannot be moved to another environment after assignment.

Historical delivery verification uses the original stored connector even when it
was previously shared across environments. New previews and publication attempts
must use a connector owned by the request's environment. An environment with
connectors cannot be deleted until unused connectors have been removed; connectors
with publication history must remain available for recovery.
