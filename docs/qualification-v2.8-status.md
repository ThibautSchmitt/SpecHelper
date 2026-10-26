# v2.8 qualification status

**Incomplete. This report does not declare v2.8 accepted.**

This is a dated snapshot of protocol 3 observations collected on 26 October 2026,
after Q01 and Q02 were closed in both configurations. It separates implemented safeguards,
native execution reliability and reviewed business accuracy.

## Protocol and coverage

The frozen analysis baseline is `bc176c9`. The reporting code is `1a4178d`;
production's model-selection correction is `3f2675b`. Reporting changes do not
replace the frozen analysis instructions or reinterpret earlier protocols.

Each configuration has the same 24 synthetic inputs: 16 analysis cases and eight
scope cases. Eighteen inputs belong to development and six to reserve. Some
reserve inputs were already executed under protocol 2. They are not described as
previously unseen. Expected answers are kept outside agent inputs.

| Configuration | Analyst and verifier | Independent counter-analyst |
| --- | --- | --- |
| `gpt-first` | Codex `gpt-6-luna` | Antigravity `claude-sonnet-4-6` |
| `claude-first` | Antigravity `claude-sonnet-4-6` | Codex `gpt-6-luna` |

Observed CLI versions are Codex 0.163.0 and Antigravity 1.4.7. Native reasoning
effort is default/unknown, rather than a controlled experimental variable.
The synthetic read-only database contains 1,001 contracts, including one
historical exception, three invoices and two settings. Its complete population
was compared with the frozen fixture before this protocol.

## Measured observations

Only Q01 and Q02 have native observations in this snapshot. These are counts of
persisted execution records, not successful complete analyses.

| Configuration | Native calls | Failed steps | Published answers | Reviewed business errors | Reviewed material omissions |
| --- | ---: | ---: | ---: | --- | --- |
| `gpt-first` | 7 | 3 | 0 | Unknown | Unknown |
| `claude-first` | 3 | 3 | 0 | Unknown | Unknown |

| Configuration | Case | Application state | Native execution seconds | Outcome |
| --- | --- | --- | ---: | --- |
| `gpt-first` | Q01 | Cancelled after one retry | 342.55 | Analyst succeeded; independent counter failed twice |
| `gpt-first` | Q02 | Cancelled without retry | 213.45 | Requirement assessment and analyst succeeded; independent counter failed |
| `claude-first` | Q01 | Cancelled after one retry | 286.82 | Requirement assessment failed twice |
| `claude-first` | Q02 | Cancelled without retry | 111.78 | Requirement assessment failed once |

All six failed steps report generic `ERROR`. Inspected native diagnostics show an empty
model response after tool activity. They do not establish exhausted Claude quota,
an authentication failure or a confirmed root cause. Failed executions without a
published answer cannot be scored as zero business errors or zero omissions.
The three independent roles remain required before publication.

| Configuration | Observed input tokens | Observed output tokens | Provider-reported total tokens |
| --- | ---: | ---: | --- |
| `gpt-first` | 432,225 across 7/7 calls | 19,152 across 7/7 calls | Unknown overall; 92,411 reported across 3/7 calls |
| `claude-first` | 61,129 across 3/3 calls | 4,170 across 3/3 calls | 65,299 across 3/3 calls |

Token fields retain their provider-reported meanings. Missing total-token fields
are not reconstructed. Monetary cost is unknown. Native execution duration is
separate from case wall time, which includes operator diagnosis gaps.

The eight deterministic scope cases matched their expected admission decisions
in both configurations without AI calls. This small synthetic sample does not
establish general false-positive/negative rates or generated-answer accuracy.
Four expectations cite fixture context rather than the application admission
policy; those references are not accepted as proof of the admission implementation.

## Diagnosis and implemented corrections

The observed Gemini quota exhaustion is scoped to Gemini's pool. It no longer
blocks the separate Claude/GPT pool. Editing a connection to another pool releases
only its old pool-specific block; target-pool and account-wide failures remain.
Actual model selection through the production HTTP API was checked without
changing the existing connection or invoking an analysis.

Four diagnostic controls outside the corpus succeeded: a minimal structured
object, a required null field, the complete requirement schema, and that same
schema after an authorized file read. These controls establish that structured
Claude completion is possible through the installed integration. They do not
explain the real-context failures or validate an end-to-end analysis. Their usage
is excluded from the qualification tables above. No schema, permission or
independent-role requirement was relaxed.

## Remaining acceptance evidence

- Complete both distributions, including reserve observations, retaining failed,
  clarification-only and missing-answer outcomes.
- Review actual final outputs independently against expected material facts,
  code/database evidence, omissions, contradictions and clarification relevance.
- Establish representative anonymized business coverage. The current corpus is
  authored synthetic data; source-derived prevoyance drafts are not customer cases.
- Obtain knowledgeable human review of expected answers and business coverage.
  Official references can support that review but do not constitute its approval.
- Produce the complete comparative error, omission, coverage, token and time
  report, and add repeatable regressions for further reproducible defects.

The scope checks and reliability safeguards have implementation/test evidence;
the full corpus, reserve and business acceptance requirements remain unproven.
See [qualification procedures](qualification.md) for collection and review contracts.
