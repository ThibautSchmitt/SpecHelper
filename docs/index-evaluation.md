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
rtk proxy python3 scripts/evaluation/reliability_benchmark.py prepare .local/my-index-study
rtk proxy python3 scripts/evaluation/reliability_benchmark.py source .local/my-index-study --case python-orders
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
rtk proxy uv run --project backend python scripts/evaluation/native_comparison.py \
  .local/my-index-study --agent codex --enable-inference \
  --output .local/native-comparison.json
```

Use `--agent claude` only when that connected provider is explicitly selected for
the whole paired run. Inference is bounded to 18 calls, 45 seconds per call and a
15-minute run deadline. Failed or partial runs retain actual attempts and usage;
they do not become successful comparison scores. Repeated launches are separate
runs and may consume additional subscription quota.

On 2026-10-24, Codex was connected but its official session window reported 100%
used and `ordinary_usage_allowed=false`; Claude was disconnected. The native
comparison therefore stopped before inference. **Analysis precision, material
false claims, critical fact omissions, detected counterexamples, ambiguous
decisions, inference duration and actual input/output tokens remain unmeasured.**
Cost remains null whenever the provider does not return a measured cost; token
counts are never inferred from characters or subscription price.

To score a completed run, supply its `responses` array to `compare --responses`.
Each response carries `case_id`, `mode`, `git_sha`, structured `output`, role usage,
elapsed time and actual tokens. Add a semantic `review` with reviewer, method,
`material_conclusions` covering every returned conclusion and `material_errors`.
The corpus supplies critical facts, forbidden universal conclusions and expected
counterexamples. Literal keyword/source checks are reported separately and cannot
substitute for semantic review. Review critical omissions and business decisions
against the actual report, not merely literal matches.

## Activation decision

Keep optional indexing disabled. Require a completed, reviewed paired comparison
on representative anonymized workloads, with measured quality and actual token
usage, before recommending activation. Reject any material quality regression
even if duration or token usage improves. Repeat the study after a source/index
version change; never reuse an index from another project or branch snapshot.
