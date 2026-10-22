# v1.3 delivery

## Preserved behavior

Keep the existing shared team instance, persistent worker queue, immutable Git
baselines and result versions, read-only analysis, provider session isolation,
clarification and continued discussion. Keep English source/documentation and
complete English/French interface catalogs.

## Delivery slices

1. Add a read-only view of persisted jobs with FIFO positions, real provider
   observations, bounded terminal history and links to the corresponding object.
2. Replace the horizontal navigation with Requests, Tickets and Settings in a
   persistent sidebar; add the independent queue panel and accessible mobile drawers.
3. Add encrypted ticket connector settings and independent GitHub, GitLab, Jira
   and GLPI adapters. Discover actual destinations, creation metadata and templates.
4. Add a human-confirmed publication dialog with editable content and target fields,
   faithful preview, metadata revision checking and persistent duplicate prevention.
5. List publications with search, platform/environment filters, pagination, external
   links and the exact immutable source version. Verify migrations, queue sharing,
   failures, permissions, reconciliation and responsive layout before deployment.

## Validation boundaries

API fixtures must follow official provider contracts and exercise all adapters,
including authentication errors, unsupported required fields and uncertain writes.
Connected-account ticket creation requires an explicit human confirmation and
must be distinguished from deterministic integration evidence in the acceptance report.

GLPI support must state the actual supported API generation and report incompatible
versions. Remote template discovery failures must not be described as successful
template retrieval. Missing mandatory business information remains for the user.

No implementation agent, repository writes, branch creation, commits, pull requests,
automatic bidirectional synchronization or environment-specific agent instructions
are introduced by the application.
