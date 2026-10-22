# v1.5 delivery

## Required behavior

Keep one business comparison checkbox. A confronted request runs exactly one
analyst and one counter-analyst, with an optional administrator-enabled verifier.
The writer remains internal. Connections can hold multiple roles; their identity,
availability, model and quota still constrain assignment at each role boundary.

Prefer a different actual model family at consecutive role boundaries and a third
unused family for verification. Same-family fallback requires administrative policy
and a visible warning; otherwise preserve the job in an explicit waiting state.
Accounts running the same model do not create diversity.

Counter-analysis must produce its own sourced conclusions before receiving the
analyst's conclusions. Each public role uses a separate terminal session and writable
directory. Only structured observations cross role boundaries. One targeted
verification is permitted within bounded invocation and time budgets.

## Work ownership and gates

| Owner | Scope | Merge gate |
|---|---|---|
| Flow | Role selection, checkpoints, instructions, comparison and bounded fallback | A→B→A, A→B→C, A→A→A, restricted roles, waiting/resume and independent-context tests |
| Runtime | Writable context isolation and deterministic Linux smoke | Actual cross-role canary isolation, read-only sources and independent CLI sessions |
| Interface | AI & Agents settings, inherited overrides, queue and request audit | English/French desktop/mobile settings, warnings, role/model visibility and existing workflows |
| Integration | Schema/API, queue projection, migration, documentation and deployment | Database preservation, complete relevant suites, reviewed publication snapshot and deployed smoke |

No hidden reasoning, repository writes, business database writes, development agent
or automatic publication is added. Human review of ticket and goal.md remains required.
