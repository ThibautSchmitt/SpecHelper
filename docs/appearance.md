# Appearance and analysis preferences

## Light, dark and system

Open **Settings → General → Appearance** to choose
**Light**, **Dark** or **System**. The preference is saved in this browser, including
page reloads and navigation. Other tabs in the same browser update when that
preference changes. Different browsers can use different themes on the same
shared instance. System mode follows device appearance changes immediately.

The same pages, fields and actions are available in every theme. An early theme
script applies the saved preference before the first paint; the React provider
keeps it current afterward. Invalid storage values fall back to System. If browser
storage is unavailable, a notice explains that the preference lasts only for the
current tab. Interface language and existing generated files are unaffected.

Instance primary color remains a shared server setting. Appearance provides
preset swatches and a custom picker; **Save settings** applies it to the instance.
Readable foregrounds and primary text are adjusted for the active theme. State
colors remain distinct: blue running, orange waiting, muted amber clarification,
green completed and red error. Text labels accompany colors.

## Simplified business forms

Requests collect an environment, type, description and optional attachments.
Request types are Automatic, Feature, Bug and Documentation. Questions offer
General, Technical, Functional and Architecture. Categories are persisted and
included in the analysis dossier; they do not grant extra technical capabilities.
The existing 20-file and 25 MB per-file limits apply. Files can be selected or
dropped, and removed before submission. A partial upload retains its draft and
resume behavior.

Search and status filters narrow the existing request/question list. Usable
question answers can be expanded in the list. Their summary, key points and
references accompany the complete versioned explanation; copy, documentation,
follow-up and request-handoff actions remain available below it.

## Automatic independent analysis

Open **Settings → AI & Agents → Analysis configuration** to enable or disable independent
counter-analysis for newly created requests and questions. Configure each
assistant's roles through **Edit**. One authenticated assistant with analyst and
counter-analyst roles can perform independent sessions; two accounts are not
required. Model diversity and verifier policy follow the existing orchestration
settings. Instructions and skills are available through the advanced controls.

There is no comparison checkbox in Requests or Questions. The backend ignores
legacy form flags and freezes the creation policy from the instance setting and
enabled authenticated counter-analyst configurations. Temporary quota exhaustion,
busy accounts or model availability do not silently downgrade the chosen intent;
the normal queue reports waiting or fallback explicitly. If counter-analysis is
disabled or no authenticated enabled counter role exists at creation, the normal
single-analysis workflow applies.

Existing requests keep their recorded policy, sessions and immutable result
versions. A request derived from a question uses the current creation policy and
its own selected category. Historical result content is never rewritten.

## Shared task panel

The desktop task panel stays available across Requests, Questions, Tickets and
Settings. Smaller viewports use the **Task queue** drawer. Groups show running
work first, then queued work, clarification pauses, completed work and errors.
Each card identifies the task, title, state, actual assistant and public role,
current stage or pause/error reason. Earlier participants are labeled **Previous
AI**; queued work is not shown as if an assistant were already executing it.
Synchronization and ticket publication show their real non-AI executor instead.

Clarification entries stay visible until the answer is supplied, even after other
jobs finish. They do not hold the worker. Grouping changes presentation only;
the existing persistent FIFO scheduler and request locks remain unchanged.
Measured position transitions last 250 ms and are disabled for reduced motion.

## Tickets and settings

Tickets lists published tickets and publication attempts with platform,
environment, status and text filters. Selecting a record shows its submitted
content, labels, immutable analysis provenance and recorded synchronization
metadata. **Refresh records** reads local records; it does not claim to fetch a
live remote ticket status or trigger an external update. Existing publication and
reconciliation actions remain on their source result and require human review.

Settings has exactly three tabs: **General** for browser appearance and instance
identity/language/color, **AI & Agents** for named assistant configurations and one
analysis configuration block, and **Environments** for Git sources, databases,
project context and environment-owned publication connectors. Connection creation forms
open only when requested, preserving space for existing configurations. The
bottom-left **Settings** shortcut is the sole settings navigation entry. Main
navigation contains Requests, Questions and Tickets. It does not invent a signed-in
application user or introduce application-level accounts. See [settings](settings.md)
for quota observations and connector migration behavior.
