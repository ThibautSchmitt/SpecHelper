# Qualification observations and unresolved limits

These dated observations are retained because failed or incomplete qualification
must not disappear when historical guides are removed. They do not certify current
models or answer quality. No independent human business acceptance was recorded.

## Native multi-role trial — closed 27 October 2026

The trial was closed with **qualification deferred**. The frozen analysis implementation
was `bc176c9`, report code `1a4178d`, with model-selection correction `3f2675b`.
The protocol used 24 authored synthetic inputs: 16 analysis subjects and eight scope
checks, split into 18 development and six reserve cases. The reserve cases had already
been exercised under an earlier protocol and were not an unseen acceptance set.

Two configurations used the same corpus: a Codex-first arrangement with a separate
Antigravity Counter-analyst, and the reverse arrangement. Recorded CLIs were Codex
0.163.0 and Antigravity 1.4.7. The selected models were gpt-6-luna and claude-sonnet-4-6;
reasoning defaults were not controlled. The database fixture contained 1,001 contracts
with one historical exception, three invoices and two settings. It was synthetic.

| Observed configuration | Analysis cases attempted | Native calls | Failed steps | Published answers |
| --- | ---: | ---: | ---: | ---: |
| Codex-first | 2 | 7 | 3 | 0 |
| Antigravity-first | 5 | 6 | 6 | 0 |

Recorded case wall times ranged from 41.30 to 342.55 seconds. Eight failures were
classified as generic errors and one as quota exhaustion. Empty output after tool use
was not evidence that quota or authentication caused every failure. Remaining analysis
cases were not executed: 14 in the first configuration and 11 in the second.
Mandatory independence and verification gates were not relaxed to produce a result.

Eight scope cases matched expectations in both configurations without inference,
but that small fixture result is not business-quality acceptance. Material-error and
omission rates were **unknown**, not zero, because no final business answers were
available for review. No successful professional or independent human review followed.

The Codex-first observations recorded 432,225 input and 19,152 output tokens over
seven calls; total-token fields were present for only three. Antigravity-first recorded
103,012 input and 5,269 output tokens over six calls. Financial costs were unknown;
reported native durations were not interchangeable with end-to-end wall time.

Prompt experiments and controlled structured-output checks did not prove that real
analysis context worked. At the time, quota observations were incomplete; that dated
limitation must not be read as the current metadata implementation's capability.
Completing qualification requires representative cases, both full configurations,
independent human review, explicit model/reasoning controls and honest failure/cost
coverage. Current automated orchestration tests do not substitute for this trial.

## Optional navigation-index comparison — 24 October 2026

The index remains an **evaluation tool, not the production navigation path**.
The closed corpus comprised fictional Python order, TypeScript stock and Java billing
projects with frozen commits. Source inspection and indexed navigation selected the
same four source files per subject; the selected source-byte counts were unchanged.
One small warm, ordered run cannot establish a general navigation or context advantage.

Machine-readable observations are retained in
[navigation-observation.json](../../scripts/evaluation/navigation-observation.json) and
[native-observation.json](../../scripts/evaluation/native-observation.json).

The native trial completed 18 calls across six analyses with gpt-6-luna. Source-only
runs reported 387,164 input and 17,745 output tokens over 279.71 seconds; indexed runs
reported 412,537 input and 16,317 output tokens over 269.08 seconds. Cached input was
included and financial cost was unknown. These figures do not establish a reliable
cost or latency improvement.

Agent-assisted semantic review found no clear false conditional business rule or
critical omission among 19 final material statements in this closed corpus. However,
strict source validation found **26 invalid citations out of 87 across roles**, including
**six out of 29 final citations**, concentrated in two Java reports. Defects concerned
excerpts and source ranges rather than different SHAs. They were not repaired after
the run to turn a failing result into a pass. The quality gate therefore **failed**.
This was not an independent human review or a representative business trial.

## Persistent-session and progress scope

Tests with fake provider transports cover ordered messages, native session identifiers,
explicit recovery, browser ownership, independent role contexts and bounded work events.
Such tests do not prove uninterrupted sessions at a live provider, concurrent entitlement,
streaming support for every model or the correctness of its answer. Provider output
shapes differ and quotas can prevent a real inference probe. Report unavailable probes
as unavailable rather than replacing them with simulated success.

For current session/progress behavior see [Architecture](../architecture.md).
For safe test commands see [Development](../development.md). Git retains the full
superseded reports; this evidence record preserves their material negative outcomes.
