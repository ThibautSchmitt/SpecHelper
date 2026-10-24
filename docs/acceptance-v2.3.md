# v2.3 acceptance evidence

Status: application validation, retrieval measurements and native model observations
are recorded separately. The native paired study completed on 2026-10-24 after
the operator-selected ChatGPT quota reset. Its exact-source quality gate **did not
pass**: the final Java reports contain invalid exact excerpts. Optional production
indexing remains disabled. Measured completion is not acceptance of every result.

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
review counts. The expanded suite passed **13 checks**, adding explicit semantic
coverage, actual native citation auditing and a guard that keeps the quality gate
failed despite complete measurements when exact source proof is invalid. Run it with:

```sh
rtk proxy uv run --project backend pytest backend/tests/test_v23_evaluation.py -q
```

Actual source navigation and actual `codebase-memory-mcp` indexing/search were
measured on Python, TypeScript and Java synthetic projects. All four expected
source files were reopened in each mode for every project. These measurements
establish retrieval on those fixtures only. They do not establish analysis quality,
representative throughput or token savings.

## Completed native observation and remaining quality gate

The real Codex comparison completed six paired analyses and eighteen independent
role invocations using `gpt-6-luna`. Each pair used the same frozen Python,
TypeScript or Java project after actual source/MCP navigation. The Counter-analyst
received no Analyst report; the Verifier received both. This is a role-level native
benchmark, not a full application or final-ticket test.

[`native-observation.json`](../scripts/evaluation/native-observation.json) records
the actual measurements, artifact hashes, review authority and limitations:

| Mode | Analyses / native calls | Actual input / output tokens | Role elapsed seconds | Invalid final citations |
| --- | ---: | ---: | ---: | ---: |
| Source search | 3 / 9 | 387,164 / 17,745 | 279.71 | 3 / 16 |
| Actual MCP navigation | 3 / 9 | 412,537 / 16,317 | 269.08 | 3 / 13 |

The total was **799,701 input tokens**, including 362,240 cached input tokens,
**34,062 output tokens** and **548.79 seconds** of role invocation time. Measured
billing was not returned, so cost remains unknown. These totals exclude earlier
schema-rejected attempts, preflight/setup, navigation and a small connectivity probe.

An accountable agent-assisted audit read all **57 material role claims**, including
**19 final claims**, against the twelve actual frozen files. It found no materially
false conditional/configuration/history conclusions in those final claims. All
24 expected critical-fact slots and twelve behavioral counterexample slots were
covered, with no business policy choice silently invented. The review distinguishes
paraphrases from literal-keyword checks and records minor terminology limitations.
It is not independent human certification or a general accuracy estimate.

A separate strict Git audit checked **87 citations** across all roles: **26 failed**
exact excerpt/range checks. Six of 29 final citations failed, three in each Java
report. Repositories and SHAs match, but indentation, punctuation or line ranges
were changed. The original outputs remain unmodified. Correct interpretations do
not waive invalid source proof; the application's evidence checks must downgrade
such claims. `complete_analysis_comparison=true` means measurements and reviews
exist; `native_quality_gate_passed=false` records this actual failed gate.

Both navigation modes supplied the same four files and identical source bytes
per project. One ordered trial, variable cache observations and one provider/model
family cannot establish causal token/time savings or representative throughput.
Keep indexing disabled. Exact provenance defects need resolution, and a repeated,
independently reviewed study on representative anonymized workloads is still required
before recommending production index activation. No live business database or
production mutation was used.
