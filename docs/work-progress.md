# Observed work in conversations

Discussion and deep analysis share a compact, expandable progress component.
An accepted discussion turn immediately shows **I’m on it…**, before any CLI
event. The worker then reports preparation, active processing and observed tool
operations. Quiet processing keeps its actual active state and elapsed time; the
interface does not invent activity to fill silence.

Deep analysis retains its single cycle element and the recorded Analyst,
Counter-analyst and Validator states. Each started role can disclose its observed
work. A tool result is marked complete only on an actual completion event; an
unrecorded end remains unknown. An execution ending does not certify its findings.

## Provider differences

| Adapter | Work observations | User-facing draft |
| --- | --- | --- |
| Codex | JSON `item.started/updated/completed` command, MCP tool, web search and plan lifecycles | Only the selected response field of an `agent_message`; the CLI may deliver this only at completion, so token-by-token text is not promised. |
| Claude Code | `stream-json --verbose --include-partial-messages`; tool calls and corresponding tool results | Incremental text from the selected JSON response field, including `StructuredOutput` input deltas when emitted. Other text and thinking blocks are not relayed. |
| Antigravity | Existing JSON `step_update` tool states | Selected structured response field when exposed by the terminal result; no unsupported token stream is simulated. |

Codex event contracts are described by its [non-interactive documentation](https://developers.openai.com/codex/noninteractive/)
and [official event types](https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs).
Claude's flags are documented in its [headless CLI guide](https://code.claude.com/docs/en/headless).
Antigravity uses the installed adapter's structured protocol; versions omitting
tool IDs cannot reliably pair start/end events. Repeated identical observations
are collapsed, and a missing end is not inferred.

## Transport and persistence

The existing authenticated runtime `/run` endpoint optionally streams bounded
NDJSON snapshots and one terminal result. Non-streaming calls and older runtime
JSON responses keep their contract. Heartbeats carry no invented work. Browser
polling remains serial: every two seconds while active, ten seconds while idle.
The narrow owner-protected `/analyses/{id}/progress?cursor=...` endpoint replaces
full-history refreshes when only progress changed. A content token triggers the
ordinary detail fetch when messages, results or orchestration state change.

Migration `0043_observed_work_progress` adds `Job.progress`, without new tables or
rewriting previous analyses. Each job retains at most 16 invocation summaries,
each with 24 recent tool observations. The public projection returns up to 50
recent jobs, bounded independently of the full conversation. Older analyses keep
their recorded role states and messages; missing old tool observations are not
reconstructed. Progress writes are throttled and fenced by the running job and
exact execution attempt. Late frames after cancellation cannot update progress.

The work data is separate from role outputs, frozen context and evidence. It is
never fed to another role. Provider sessions, independent review, read-only
resources, quota refreshes and ticket publication gates keep their existing paths.

## Display boundary

Only allowlisted operation categories and terminal states cross the observation
boundary. Commands, arguments, paths, source content, private reasoning and plan
text do not. A draft decodes only the explicitly selected user-facing JSON string,
never JSON fragments or arbitrary intermediate messages. Known credentials and
their unfinished prefixes are filtered before release. Drafts are labelled
**pending validation**, disappear on interruption and are replaced by the accepted
answer. They do not become a verified result or ticket.

Completed observations remain expandable after reload. A lost browser connection
shows **Progress updates unavailable** and stops the activity animation until
tracking returns; it does not claim the agent failed. Actual provider failures,
quota waiting, cancellation and partial verification retain distinct states.

## Validation on 2026-10-30

- Backend suite: 1,372 passed, 19 environment-dependent skips; the existing
  Starlette/httpx deprecation warning remains.
- PostgreSQL: 31 passed, covering observations, ownership, cancellation fencing,
  competing messages, deep launch races and scheduler admission.
- Browser regressions: 60 conversation cases passed in French/English on desktop
  and mobile. The 12 observed-progress cases also passed against the
  compiled Docker frontend, including scroll anchoring during streamed drafts,
  with API fixtures for controlled lifecycle states.
- Subsequent targeted checks: 36 passed, including interrupted transport, missing
  terminal response, duplicate frames and rejected private fields.
- TypeScript, Ruff, Django system checks, migration drift checks and production
  frontend build passed. Migration 0043 was applied after a database backup.
- A live-provider smoke was attempted through the deployed application. Both
  configured connections, Codex and Antigravity, reported `QUOTA_EXHAUSTED`;
  there was no configured Claude connection. No model invocation or synthetic
  conversation was created by that smoke. Live progress and incremental response
  behavior remain to be confirmed when a configured provider becomes available.

Runtime fixtures exercise captured CLI JSONL and the terminal contract for Codex
and Claude. Antigravity tool-step normalization is covered by protocol fixtures;
this is not a claim of live subscription execution or token streaming.
