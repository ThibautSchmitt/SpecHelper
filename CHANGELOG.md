# Changelog

Entries describe source implementation, not automatic deployment or universal quality.
Detailed dated evidence remains in the [archive](docs/archive/README.md).

## Unreleased

### Persistent discussion and on-demand deep analysis

- Start new Analyses with one conversational assistant and persist native CLI
  context/IDs. Resume Codex, Claude Code and Antigravity using their own adapters;
  explicitly recover missing sessions from stored history without silently changing models.
- Launch the existing independent three-role pipeline only on explicit deep-analysis
  or ticket preparation, with fresh role sessions and frozen human context.
- Keep post-result discussion separate from immutable result versions; preserve
  readable historical dossiers, optional reports and existing publication approval.
- Add browser-owner isolation for new conversations under existing instance auth,
  revision-checked submissions, fenced cancellation and additive migration 0042.
- Keep factual clarification answers out of the normative business decision ledger.

### Clarification resumption

- Invalidate superseded checkpoint completion fences after a revised answer while
  retaining their recorded evidence and the current no-progress protections.
- Expose the latest user answer explicitly to each analysis step; reject repeated
  answered questions even when they use new identifiers, and clarify factual intent.
- Place resumed progress after the latest input and remove sender labels, user
  avatars and clarification-detail disclosures from the conversation.

### Review response validation

- Explain cross-field review rules in the schema and use review-specific bounded
  correction instructions. A requested focused check must remain explicit rather
  than being silently discarded to accept an inconsistent approval.

### Analysis deletion and shared interface

- Add confirmed analysis deletion from the detail page; remove deleted dossiers from
  discovery and Activity while retaining published-ticket provenance and linked history.
- Require running agents to stop before deletion and preserve publications in progress.
- Use the AI Connections screen as the shared visual reference: quiet surfaces,
  thin borders, restrained controls and rounded semantic tags in both themes.

### Business conversation

- Use a plain assistant icon, tighter spacing and a compact three-stage progress block.
- Show one accepted business answer; keep individual recorded-role reports as optional
  Markdown downloads in the final report, separate from ticket attachments.
- Format explicit role mentions in assistant questions and answers as colored tags.

- Keep the configured instance as the single visible assistant; expose original role attribution only in clarification details.
- Update one expandable progress message per investigation cycle with recorded stage completion and observed resource-wait causes, preserving partial-result limits.

- Recover historical clarification authors from matching saved questions and accepted execution history without rewriting messages or using current account settings.

- Present needs, clarifications, answers and versioned conclusions in a single business conversation.
- Keep actual role attribution, accepted structured reports and technical provenance expandable behind the single assistant.
- Move report details and deliverables out of the main thread while preserving partial-result limits, publication review, decision conflicts and independent analysis.

### Native analysis policy and progress safeguards

- Remove global prompt editing and the total AI-call setting from standard
  administration. Continue progressing checkpoints regardless of stored call totals;
  stop empty or repeated transitions while retaining validated observations.
- Supply conditional official-source consultation natively, preserving automatic
  evidence receipts and technical sandbox/read-only controls.
- Archive retired guidance without duplicate execution; preserve nonstandard safe
  text as inactive custom skills for review and support an optional deployment file.
- Distinguish read-only built-in skills from fully editable custom procedures,
  preserving previous revisions and customized content during migration.

### Role coverage cards

- Show Analyst, Counter-analyst and Verifier side by side in Orchestration,
  with coverage badges and the named AI connections eligible for each role.
- Keep configured coverage separate from temporary availability; stack the cards
  on smaller screens without changing scheduling or assignment rules.

### Consistent buttons and tags

- Keep the Activity toggle at the same page position when its panel opens and
  remove the duplicated panel title, retaining accessible panel labels.
- Share a slightly rounded rectangular shape across action buttons and menus.
- Use fully rounded tags across Activity, analyses, tickets, AI connections,
  role coverage and environments, retaining existing status colors and actions.

### Explicit CLI maintenance

- Detect actual runtime CLI versions and check official stable releases automatically;
  show the installed version above each connection's Quotas disclosure.
- Offer an explicit Update action, queue it behind running invocations and sign-ins,
  validate activation and retain the previous executable for rollback.
- Isolate installation in a dedicated maintenance service without application
  credentials or Docker access; mount managed tools read-only in the AI runtime.
- Hide separate reasoning controls for Antigravity, whose model identifiers already
  encode their supported reasoning variants.

### Clearer model catalog feedback

- Show plain model names without discovery/access labels or explanatory catalog
  text; keep the refresh action, loading indicator and failure feedback.
- Select medium reasoning when supported, retain existing explicit choices, and
  use only native supported alternatives when medium is unavailable.
- Remove the redundant assistant selector from connection editing; keep the
  assistant choice when creating a connection and retain access evidence internally.

### Light and dark theme consistency

- Keep the same illustrated Home, filled Activity actions, button typography and
  synchronization badges in both themes, using readable theme-specific colors.
- Make Tailwind dark variants follow the application preference rather than the
  operating-system theme. Verify layout parity in English/French on desktop/mobile.

### Model refresh and navigation follow-ups

- Keep complete quota windows in a closed Quotas disclosure on each AI card,
  preserving shared-identity observations, model-pool labels and refresh behavior.
- Shorten quota periods, hide technical quota sources/limit IDs, order Gemini
  before Claude/GPT windows, and remove repeated provider/account metadata.
- Show exhausted quotas as an empty progress bar with 0% remaining inside AI
  connection cards, preserving unknown observations and independent model pools.
- Show a red exhausted-quota badge before Edit only for total weekly exhaustion:
  a global weekly limit, or both Antigravity Gemini and Claude/GPT weekly pools.
  Session exhaustion, a single exhausted pool and missing data do not trigger it.
- Show the model/effort and each permitted role as distinct colored tags beside
  connection status, reusing its badge design while keeping both themes readable
  and long names responsive.
- Keep role tags in Analyst / Counter-analyst / Verifier order regardless of the
  stored assignment order or the order in which checkboxes were toggled.
- Preserve a scheduled quota refresh when polling lands on its reset boundary.
- Open the connection editor inside its own card, retaining explicit save/cancel
  and the existing creation form, model discovery and role configuration. A
  second click on Edit cancels unsaved edits and closes that card's form.
- Remove redundant connection-detail and role disclosures from AI cards, keeping
  the assigned roles directly visible and editable through the existing form.
- Remove selection-priority and participation controls from the connection form;
  preserve stored priorities and keep activation in the existing action menu.
- Clarify existing connection actions as Change account and Refresh status and
  quotas, preserving the authorization and metadata checks they already perform.
- Ignore expired authentication attempts when guarding model/connection operations,
  while preserving active-login and busy-analysis protection across shared identities.
- Keep administration access in the bottom-left button, remove redundant sidebar
  shortcuts, and remove diagnostics from Activity cards.
- Apply the same hover/focus treatment to Activity, Analyses and Tickets, with
  reduced-motion support and unchanged ticket selection/publication behavior.

### Dashboard reference styling

- Match the supplied visual direction with navy surfaces, turquoise actions,
  illustrated Home, colored analysis/activity cards and administrative shortcuts.
- Show observed quota summaries on connection cards, with detailed windows kept
  expandable and real role coverage/active-skill counts alongside connections.
- Open environment creation on demand and keep theme, language, native metadata,
  publication confirmation and the independent analysis pipeline intact.
- Carry Home drafts privately to the existing creation form; preserve explicit
  Light/System preferences and default new browsers to Dark.

### Focused interface simplification (post-v2.9)

- Reduce each sidebar assistant to one status/quota link, retaining model-pool
  boundaries, the limiting applicable window, stale cues and metadata-only refresh.
- Rename the shared panel Activity, close it by default for new preferences, count
  only actionable items, and place execution diagnostics behind disclosures.
- Make Home categories disjoint, keep partial results explicit and preserve old
  actionable errors and pre-job scope questions without creating scheduler jobs.
- Add short local title proposals and an editable presentation title without
  replacing the original need or immutable results; show recorded family diversity.
- Use Edit plus secondary-action menus, simplify settings into four sections,
  reuse shared Git/PostgreSQL connections and record connector test timestamps.
- Clarify synchronization, queue/resource waits and English/French system labels;
  preserve authentication, role ordering, quotas and human publication confirmation.

### Clearer AI configuration and ticket actions (v2.9.1)

- Stop short configured credentials from replacing fragments of ordinary interface
  words or falsely rejecting instructions. Preserve exact-value, encoded-token and
  URL credential redaction, and keep redaction markers stable across repeated passes.
- Replace the default/preference combination with one numeric selection priority,
  migrating existing ordering and retaining deprecated API compatibility.
- Show global coverage of mandatory roles and reject new independent analyses
  with missing configured roles before invoking an assistant. Keep quota and
  capacity waits separate from configuration validity; incomplete settings remain savable.
- Unify participation with connection activation, preserve disabled role choices,
  and explain instruction precedence without changing security or role execution.
- Add an explicit Cancel action to ticket preparation, preserving edited drafts.
  Explain publication blockers and missing fields next to the disabled creation action.

### Antigravity usage and settings recovery (v2.9.1)

- Read native Antigravity `/usage` JSON without inference. Keep Gemini and Claude/GPT
  quotas, reset timestamps and scheduler recovery separate by model pool.
- Replace the neutral Antigravity icon with the official locally bundled color mark.
- Keep administration readable when stored instructions trigger credential validation,
  explain required roles and show a localized review warning. Preserve stored text
  and strict execution validation; never silently clear rejected instructions.

### Native provider metadata and focused settings (v2.9.1)

- Keep arbitrary observed quota windows, credit units and provider/model limits
  separate; refresh metadata after invocations, authentication and known resets
  without inference probes or changes to active capacity leases.
- Configure native identity-scoped model and reasoning choices on each AI
  connection. Keep previous catalogues on failure and legacy configurations intact;
  remove the global Models tab. Freeze explicit reasoning in session snapshots.
- Move new analysis creation to Analyses, keep Home focused on resumption, and
  preserve old creation/question-transfer links.
- Separate General, AI & Agents, Sources & environments and Connectors; retain
  per-environment publication permissions. Document native OAuth options without
  claiming unimplemented browser publication flows.
- Record native Codex and Antigravity metadata checks and Claude initialization
  protocol evidence; account quotas for Claude remain Not reported. Native
  Antigravity usage handling is described above.
  See [provider metadata](docs/provider-metadata.md) for exact verification limits.

### UX polish (v2.9.1)

- Remember the collapsed activity panel across navigation and reloads; keep
  clarification/action indicators visible and preserve live queue updates.
- Keep one activity card per analysis and at most five recent completed cards,
  with access to history. Separate recorded AI work from user and resource waits.
- Clarify Home's attention, available-result and active sections, including partial
  results and reported limits. Bound list titles and summaries to two lines while
  retaining full keyboard link names, details, filters and historical URLs.
- Retain quota thresholds and metadata-only refreshes; move secondary dates into
  accessible disclosures and flag stale observations compactly.
- Separate authentication, availability and quota. Move numeric preference and
  the call-loop safeguard into collapsed advanced options; keep roles visible.
- Harmonize French skill terminology and business-result labels. Provider
  selection, independent roles and ticket publication behavior remain unchanged.

### Unified analysis experience and reviewed diagrams (v2.9)

- Add Home and a searchable, filtered, paginated Analyses list while retaining
  historical Question and Request URLs and their immutable results.
- Infer understanding/change/mixed intent from one free-text entry and preserve
  mandatory independent analysis, counter-analysis and verification.
- Keep a chronological business history and dated need revisions; guard concurrent
  edits, preserve confirmed decisions and block stale-result approval/publication.
- Create retry-safe linked changes from selected answers, retain attributed source
  context and reanalyze against the selected environment's current Git baseline.
- Distinguish processing, partial results, unavailable verification, prepared drafts
  and actual publications; place business conclusions before expandable evidence.
- Retain structured diagrams only after independent relation review and accepted
  Git/SQL evidence for existing relationships. Keep hypotheses and proposals explicit.
- Render diagrams on demand with zoom, alternative text, source copying and a
  readable failure fallback; export Mermaid with reports and development goals.
- Offer an explicitly selected diagram annex for standard tickets at destinations
  supporting file uploads, preserving existing templates, edits and timeout recovery.

### Project scope and qualification groundwork (v2.8, implementation frozen)

- Check Request and Question scope before reserving providers or queueing analysis.
- Preserve original text and follow-ups during recoverable clarification or reformulation.
- Add revision-checked scope editing and English/French interface messages.
- Add 24 explicitly synthetic qualification cases, a separate reserve and frozen
  Git/database packets with independent review and measured-usage contracts.
- Keep missing measurements unknown and qualification unapproved until reviewed.
- Keep requirement-stage AI findings out of the counter-analyst's blind exploration,
  while retaining the original need, confirmed user choices and frozen project context.
- Collect actual application steps with separate development/reserve results;
  reject model/version or frozen-input substitutions and retain failed-call usage.
- Accept short project actions and contextual follow-ups without admitting unrelated
  personal tasks; cover both workflows and languages on desktop and mobile.
- Allow Antigravity to inspect its exact service-authored output schema while
  keeping the rest of its session directory outside the file-read grants.
- Enqueue frozen cases through an explicitly isolated application database, with
  reserve selection and model/source checks before creating normal analysis jobs.
- Measure scope admission even when clarification prevents an analysis job.
- Preserve verification limits in published results while removing private runtime
  paths from evidence prose; retain exact source excerpts and query receipts.
- Publish the final independently reviewed business summary, including fields
  deliberately left empty, instead of restoring unverified exploration assertions.
- Accept private qualification corpora with explicit provenance/privacy records,
  declared repositories, preserved clean Git commits and a dated database fixture;
  keep expected answers and review metadata outside agent packets.
- Clarify exact repository-relative citations, frozen environment names and structured
  Question answers after observed native citation/format failures; retain strict
  rejection and bounded repair instead of guessing paths or publishing invalid output.
- Retain observed quota exhaustion when periodic refresh has only unavailable metadata
  or low usage figures; recover automatically only from an actually expired exhausted
  window or explicit provider permission.
- Keep Antigravity's Gemini quota independent from its shared Claude/GPT quota.
  A known-model failure blocks its pool; an unscoped account failure stays global.
- Re-evaluate a connection's model-pool block when its selected model changes;
  preserve exhausted target pools and account-wide restrictions.
- Report observed execution failures and published-answer availability separately
  from reviewed business errors; retain unknown native-call counts and safe diagnostics.
- Document a dated comparison snapshot with actual failed calls, missing answers,
  usage coverage and explicit remaining business/reserve review requirements.

The implementation iteration was closed at the maintainer's request on 27 October
2026. Expert review, further Antigravity runs and completion of comparative/reserve
qualification are deferred to follow-up work and do not block subsequent development.
Existing measurements remain partial; this decision does not certify analysis
accuracy. See [qualification groundwork](docs/qualification.md).

### Antigravity provider (v2.7)

- Add Antigravity to existing AI connections, exact model discovery and role selection.
- Pin native Linux CLI 1.4.7 and verify its official binary checksums.
- Add official Google account authorization with encrypted native OAuth credentials
  and a separate optional Gemini API mode with explicit billing consent.
- Keep reusable credentials outside analysis children; no host account import or
  implicit paid fallback is used.
- Preserve fresh native conversations, global skills and the existing step scheduler.
- Retain permission grants/observations separately; refused or failed necessary tools
  cannot become complete results or publish external tickets.
- Add real-CLI sandbox probes with synthetic Gemini transport and EN/FR browser coverage.

An authorized Google-account probe executed the discovered Gemini 3.8 Flash (Low)
model with actual source/global-skill reads and structured output on 2026-10-25.
Controlled tests cover three-family orchestration; representative accuracy, live
three-account throughput, monetary cost and missing quota remain unproven.
See the [provider contract](docs/antigravity.md).

### Documentation consolidation (v2.6)

- Consolidate active product, architecture, configuration, analysis and operations guides.
- Shorten the README around business value and the checked installation path.
- Inventory and archive older documents; retain security conditions and open limitations.
- Add documentation link/anchor and shell-example checks and maintenance rules.
- Verify startup with clean application volumes isolated from the existing instance.
- No application behavior, security policy or provider changes.

## v2.5 - 2026-10-24

Free-text entry; compact attachments; persistent ticket drafts, actual templates/types,
concise format, exact previews and explicit per-file delivery; conditional public
references with receipts; clearer queue/completeness/diagnostics; portable skills,
detected models and observed quotas.

See the [v2.5 report](docs/archive/reports/acceptance-v2.5.md) for controlled validation
and live vendor-write limits.

## v2.4 - 2026-10-24

Persistent scheduling per compatible AI step, cross-request concurrency, shared-account
leases and sequential per-request checkpoints; cancellation/retry/recovery without a
fixed total business deadline; lazy global skills, two instruction levels and independent
omission discovery. See [v2.4 evidence](docs/archive/reports/acceptance-v2.4.md).

## v2.3 - 2026-10-24

Mandatory independent Analyst, Counter-analyst and Verifier; scoped Git/SQL evidence;
source/index evaluation. Native measurements completed, but exact-citation quality
failed, leaving production indexing disabled. See [limitations](docs/known-limitations.md)
and [v2.3 evidence](docs/archive/reports/acceptance-v2.3.md).

## v2.2 - 2026-10-24

Guided business choices, decision history, explicit contradiction review, targeted
reanalysis and human validation. See [v2.2 evidence](docs/archive/reports/acceptance-v2.2.md).

## v2.0-v2.1 - 2026-10-23

Versioned declarative library/model metadata, then conversational creation, inactive
drafts, explicit activation, sandbox demonstrations and import/restore.
Current global-skill rules supersede manual assignments.
See [v2.0](docs/archive/reports/acceptance-v2.0.md) and
[v2.1](docs/archive/reports/acceptance-v2.1.md).

## v1.9 - 2026-10-23

Shared access protection, encrypted credentials, isolated provider execution, input
hardening and executed security checks with residual findings.
Current conditions: [security validation](docs/security-testing.md);
dated evidence: [v1.9](docs/archive/reports/acceptance-v1.9.md).

## v1.0-v1.8 - 2026-10-20 to 2026-10-22

Initial requests, Git baselines, clarification, immutable results; English/French;
ticket connectors; multiple Git/AI configurations; environment documents; Questions
and handoff; appearance and task panel. The [archive index](docs/archive/README.md)
links every version. Older timeout, optional-role, type and assignment rules are
historical and superseded by active references.
