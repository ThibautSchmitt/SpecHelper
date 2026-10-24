# v2.3 acceptance evidence

Status: implementation validation and measured navigation evidence are separate
from native model quality acceptance. The latter remains pending while no
connected provider has ordinary usage available. The operator chose to wait for
the ChatGPT quota reset rather than connect another provider.

## Reliability requirements

| Requirement | Validation boundary |
| --- | --- |
| Independent analyst, counter-analyst, verifier | Protocol tests must prove independent contexts and that analyst output cannot bypass verification. |
| Available family alternation | Selection tests must distinguish model diversity from one-account sequential independence. |
| Limits and counterexamples | Structured evidence and native report review must inspect quantifiers, time, configuration and alternate paths. |
| Optional database cross-check | Read-only scoped query evidence and honest absent/inaccessible database reporting. |
| Facts, interpretations, decisions, contradictions, unknowns | Strict evidence schema and result rendering; historical anomalies are qualified. |
| Material contradiction handling | Targeted check or guided clarification; no invented business decision. |
| Honest reliability limits | No artificial numerical confidence; actual limitations retained. |
| Reusable navigation | Versioned `effective-navigation` skill, preserving existing custom library content and permissions. |
| Optional source index | Fixed-SHA corpus, wrong-SHA/cross-project rejection, actual MCP observations; production activation remains disabled. |
| Queue visibility | Existing queue isolation and public role/phase remain visible. |

See [analysis reliability](analysis-reliability.md) for intended behavior and
[index evaluation](index-evaluation.md) for the measurement method. This table
defines validation boundaries; it does not imply every boundary has completed
native acceptance.

## Completed application checks

The complete backend suite passed 668 tests with one existing capability skip.
Two additional public-answer resume tests then passed for Requests and Questions,
checking protocol adoption and preservation of the confirmed human decision.
It includes real frozen Git provenance, minimized read-only PostgreSQL observations,
mandatory role isolation, contradiction handling and historical migration preservation.
The frontend passed 40 new evidence scenarios and 36 existing regression scenarios
across desktop/mobile layouts and both languages. TypeScript and the production
build passed. Ruff passed; migration generation reported no model changes.
Publication checks found no secrets and no findings or parse errors from six
local Semgrep rules covering 167 production files. Browser/provider workflow data
is controlled; these checks do not establish native model quality.
A subsequent scope audit also checks that missing observation periods, blank
conditions/population/limits and mismatched environments cannot remain supported
material conclusions or enable business validation.

## Completed evaluation checks

The standalone evaluation test suite initially passed nine checks: reproducible
Git fixtures, refusal to overwrite a study, rejection of wrong index/source/project
identity, rejection of paths outside the authorized repository, null missing usage,
separation of literal screening from semantic precision, and complete semantic
review counts. Run the current suite with:

```sh
rtk proxy uv run --project backend pytest backend/tests/test_v23_evaluation.py -q
```

Actual source navigation and actual `codebase-memory-mcp` indexing/search were
measured on Python, TypeScript and Java synthetic projects. All four expected
source files were reopened in each mode for every project. These measurements
establish retrieval on those fixtures only. They do not establish analysis quality,
representative throughput or token savings.

## Pending native acceptance

The paired native benchmark requires six analyses with three independent roles
each, then semantic review of every material conclusion against frozen sources.
Required measurements include precision, material false claims, critical omissions,
counterexamples, ambiguous decisions, elapsed duration and actual input/output
tokens. Provider cost is recorded only if measured billing is available.

The 2026-10-24 preflight observed Codex connected with its session quota exhausted
and ordinary usage disallowed; Claude was disconnected. No model inference was
performed for this benchmark. All native quality/token comparisons remain pending,
and optional indexing remains disabled. Controlled protocol tests cannot satisfy
this real-provider quality criterion. Re-run the bounded opt-in harness once an
authorized provider becomes available and retain partial failures honestly.
