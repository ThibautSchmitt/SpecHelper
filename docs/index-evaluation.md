# Optional source index evaluation

The structural index remains an optional navigation aid. It cannot replace source
evidence or authorize access to another repository, environment or Git version.
No production index integration is enabled by this evaluation.

## Reproducible corpus

The committed corpus under `scripts/evaluation/corpus/` contains three fictional
projects. They contain no customer sources, credentials or personal records.
Each project includes a rule, a configuration or temporal restriction, an alternate
import path and historical records that must not be mistaken for current policy.

| Project | Frozen Git SHA |
| --- | --- |
| Python orders | `3c9bb5247fea8387187ee0c4fd5871a3e2ac7491` |
| TypeScript stock | `5faa2a2acb6a2e60f46586fe4da0c3d4248f2852` |
| Java billing | `edfb1c837d951a68c080f0d36d167fa4852b36bb` |

The generated manifest is authoritative. It includes the full commit and SHA-256
of every source file. The runner rejects dirty sources, wrong commits, mismatched
index manifests and paths outside the authorized project.

```sh
python3 scripts/evaluation/reliability_benchmark.py prepare .local/my-index-study
python3 scripts/evaluation/reliability_benchmark.py source .local/my-index-study --case python-orders
```

Repeat source navigation for `typescript-stock` and `java-billing`. For index mode,
actually call `codebase-memory-mcp.index_repository` separately for each frozen
repository, then `search_graph` scoped to its project. Locate JSON/configuration
files with bounded file search when the graph does not cover them. Record the
real tool observations, project ID, authorized relative paths, elapsed navigation
time, commit and source hashes. Import this record with `import-index --record`.
The runner reopens the actual sources after navigation; graph hits alone are not
proof. A recorded tool name is provenance, not cryptographic attestation: reviewers
must inspect the retained actual tool observations.

## Observed navigation study

[`navigation-observation.json`](../scripts/evaluation/navigation-observation.json)
records the actual observation on 2026-10-24. The MCP tool indexed all three real
fixture repositories and returned actual symbol hits. Both modes then reopened
the same four relevant source files in each project.

| Project | Source search, seconds | MCP search, seconds | Relevant files, both modes | Source bytes, both modes |
| --- | ---: | ---: | ---: | ---: |
| Python orders | 0.01756 | 0.01001 | 4/4 | 748 |
| TypeScript stock | 0.01656 | 0.00901 | 4/4 | 849 |
| Java billing | 0.01686 | 0.00601 | 4/4 | 795 |

Retrieval precision and recall were 1.0 in both modes on this closed corpus;
critical source omissions were zero. These are **source retrieval measurements**,
not correctness scores for generated analyses. Timing covers one warm navigation
observation and excludes index construction and setup. The tiny fixtures and lack
of repetitions do not establish a performance advantage. Identical source bytes
provide no demonstrated context reduction.

## Native analysis comparison

The opt-in harness runs the same three independent roles for all six paired
contexts: analyst, counter-analyst and verifier. The counter-analyst receives no
analyst output; the verifier receives both reports. Each role uses a fresh native
context. The same explicitly selected provider identity is used for both modes.
Only synthetic files are copied into isolated workspaces. The application queue
must be idle, shared identity availability is reserved, and ordinary provider
usage must be available. There is no automatic provider fallback.

```sh
uv run --project backend python scripts/evaluation/native_comparison.py \
  .local/my-index-study --agent codex --enable-inference \
  --output .local/native-comparison.json
```

Use `--agent claude` only when that connected provider is explicitly selected for
the whole paired run. Inference is bounded to 18 calls, 45 seconds per call and a
15-minute run deadline. Failed or partial runs retain actual attempts and usage;
they do not become successful comparison scores. Repeated launches are separate
runs and may consume additional subscription quota.

On 2026-10-24, the initial session quota block was followed by a successful
operator-authorized run after reset. The eighteen real calls completed six analyses
with `gpt-6-luna`. The [native observation](../scripts/evaluation/native-observation.json)
contains exact per-project usage, durations and review limits. Source mode used
387,164 input / 17,745 output tokens over 279.71 seconds; MCP-context mode used
412,537 input / 16,317 output tokens over 269.08 seconds. Input totals include
provider-reported cached tokens. Monetary cost remains null because no measured
billing was returned.

All nineteen final material statements were reviewed against the actual frozen
sources, with no materially false conditional rule found and no missing critical
behavioral fact in the closed corpus. This was an accountable agent-assisted audit,
not independent human certification. Across eighteen reports, strict source checking
found 26 invalid citations out of 87; six invalid citations remained in the two
final Java reports. The defects involve exact excerpts and ranges, not wrong project
SHAs. No generated proof was repaired. The native quality gate therefore failed,
although the measurement run completed. See [acceptance evidence](archive/reports/acceptance-v2.3.md).

One ordered trial with identical retrieved source bytes and differing cache usage
does not establish that indexing saves time/tokens or preserves quality on a
representative workload. The production index remains disabled.

To score a completed run, supply its `responses` array to `compare --responses`.
Each response carries `case_id`, `mode`, `git_sha`, structured `output`, role usage,
elapsed time and actual tokens. Add a semantic `review` with reviewer, method,
`material_conclusions` covering every returned conclusion and `material_errors`.
The corpus supplies critical facts, forbidden universal conclusions and expected
counterexamples. Literal keyword/source checks are reported separately and cannot
substitute for semantic review. Review critical omissions and business decisions
against the actual report, not merely literal matches. Record explicit per-fact,
per-counterexample and business-decision reviews. `audit_native_sources` separately
checks every role citation against the actual frozen Git files. A complete measurement
set never overrides a failed exact-source quality gate.

## Activation decision

Keep optional indexing disabled. Require a completed, reviewed paired comparison
on representative anonymized workloads, with measured quality and actual token
usage, before recommending activation. Reject any material quality regression
even if duration or token usage improves. Repeat the study after a source/index
version change; never reuse an index from another project or branch snapshot.
