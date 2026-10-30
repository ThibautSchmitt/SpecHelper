# Persistent conversation validation

Recorded on 2026-10-30. These observations distinguish application tests from
live-provider capability; they are not a claim of universal model accuracy.

## Implemented path

Analyses creates one exploratory discussion. Further messages resume that native
context. **Launch deep analysis** freezes human input and starts the existing
independent Analyst, Counter-analyst and Validator contexts. The discussion's
assistant hypotheses are not promoted to evidence. After a result, discussion
continues without rewriting it or restarting the independent pipeline. Ticket
preparation and publication retain their existing review and confirmation gates.

Migration `0042_persistent_discussion` adds a JSON field and one status, without
new tables or historical data rewrites. Historical dossiers retain their original
shared visibility. New dossiers and their linked evolutions retain browser-owner
isolation. This deployment has no individual accounts: a different browser or a
cleared owner cookie cannot establish the same human identity. See
[ownership limitations](analysis.md#ownership-and-historical-compatibility).

## Provider observations

| Provider | Implemented native continuation | Validation |
| --- | --- | --- |
| Codex | `exec ... resume <thread-id> -` | Two live turns through the deployed application, with a browser reload. Same native ID and context; the second turn recalled a marker supplied only in the first. No deep run or result version was created. |
| Claude Code | `--resume <session-id>` | Runtime command, isolated mount and structured response fixtures pass. No configured Claude connection was available for a live subscription test. |
| Antigravity | `--conversation <conversation-id>` | Runtime command, isolated mount and structured response fixtures pass; the installed CLI exposes the continuation flag. Both observed model-pool weekly quotas were exhausted, so live continuation was not exercised. |

The Codex smoke used the configured model `gpt-5.6-luna`. The synthetic conversation
was logically deleted after the test. It published no ticket or document. Normal
post-invocation quota observations continued to update. Missing-session recovery
is tested with an explicit provider failure, rather than pretending the live
provider lost a session.

## Regression coverage

- Complete backend suite: 1,349 passed, 19 environment-dependent skips. One
  Starlette/httpx deprecation warning remains. Subsequent focused checks cover the
  browser actor passed when revising a historical dossier's need.
- PostgreSQL integration: 31 passed, including persistent discussion, competing
  submissions, a deep-launch/message race and existing scheduler lease tests.
- The 20 dedicated browser cases also pass against the compiled application on
  port 3000. Browser checks cover French/English and desktop/mobile: single-assistant turns,
  reload, explicit deep launch, continuation after a result, scope clarification,
  localized errors, cancellation, existing historical conversations, quotas,
  connector controls, ticket lists, provenance and optional role exports.
- Runtime fixtures cover native continuation commands for all three providers,
  isolated session mounts, fixed missing-session errors without raw diagnostics,
  read-only restrictions and the existing execution contract.
- Django system/migration checks, TypeScript checking, the production frontend
  build and Ruff with the backend configuration pass.

These checks do not prove live Jira/GLPI/GitLab publication or deep analysis by
three live providers in this delivery. Existing publication contracts and adapter
tests remain the regression evidence; no external ticket was created as a smoke
test. No native session, provider availability or verified conclusion is simulated
in the deployed application.
