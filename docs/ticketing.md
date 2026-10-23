# Publishing tickets

Publication is a separate backend operation. Analysis agents cannot invoke it.
An explicit **Create ticket** confirmation is required for every publication.

## Set up a connector

In **Settings → Environments**, find the relevant environment, add a named ticket
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
template-driven creation and reconciliation. See the [v1.3 acceptance report](acceptance-v1.3.md)
for verification boundaries and the other platforms' contract-test coverage.

## Review and create

Open a completed result version and select **Publish ticket**. Choose a configured
connector belonging to that environment, an allowed project and any available template or issue type. The title
and description come from that immutable result. Edit them, complete the target's
required fields and inspect the preview before confirming creation.

Field mapping uses known ticket sections and preserves target defaults. Unknown
mandatory business information is left for the user. The server rechecks access,
allowed values and template revisions before sending. If the template changed,
review a fresh preview instead of sending the old payload.

GitHub and GitLab use Markdown. GitHub YAML form fields become Markdown sections.
Jira descriptions use ADF text paragraphs and GLPI descriptions use escaped HTML;
their preview shows literal text rather than promising Markdown formatting.
Filenames, code identifiers and source quotations remain unchanged.

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
  and [issues](https://docs.gitlab.com/api/issues/)
- [Jira Cloud issue creation and metadata](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
- [GLPI legacy REST API](https://github.com/glpi-project/glpi/blob/11.0/bugfixes/apirest.md)

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
