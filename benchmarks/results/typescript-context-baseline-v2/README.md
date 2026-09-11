# Current retrieval baseline — protocol v2

Recorded 11 September 2026. All 51 fresh A-only attempts are retained. Every
final answer matches the v2 oracle; 38 attempts pass the full run criteria.
The repaired protocol provides much clearer source and response-cost evidence,
but this batch **does not supply a usable positive read-reduction comparator**.
No candidate expansion, B/C run or retrieval improvement is claimed.

| Group | Attempts | Oracle-matching answers | Fully passing runs | Tasks passing 3/3 |
| --- | ---: | ---: | ---: | ---: |
| Fixture controls | 42 | 42 | 33 | 8/14 |
| Maintained Anvil tasks | 9 | 9 | 5 | 1/3 |
| Total | 51 | 51 | 38 | 9/17 |

A fully passing run requires both an exact answer and compliance with the frozen
execution, budget, delivery and attribution rules. The 13 failed runs all have
matching final answers. They remain failed, with all recorded costs. There were
no timeouts, provider-outage replacements, correctness retries or scoring changes
after the first measured attempt.

## What v2 established

The protocol and harness were committed and published at
[`529aac8`](https://github.com/Phluxxed/loci/tree/529aac8f966681817d57c743e268cd5828078b21)
before any new measured request. It clarified the declared-parameter and emitted-
message questions, separated exact declaration bodies from required origin
headers, removed unused evidence-member requirements, and recorded delivered
signatures only with exact source provenance. See the
[protocol and complete change list](../../corpora/typescript-context-v2/README.md).

The 17 tasks and all source archives, production retrieval code, requested model,
budgets and numerical acceptance thresholds remain unchanged from v1. Source
coverage now counts the authored body without requiring an omitted export prefix
or trailing newline. It still rejects omitted internal members, wrong-file
substitutes and missing required import/export evidence. These are conservative
required spans, not a claim to have identified minimal sufficient evidence.

The separate delivery ledger retains rejected attempts without creating valid
causal events. Fifty of 51 runs have complete verified response accounting,
including **all nine maintained runs**. Invalid attribution remains a failure
when its output cost is known. The historical v1 package, raw attempts and strict
scores are unchanged. Differences between v1 and v2 are not a paired retrieval
comparison and cannot establish a runtime gain.

## Read-reduction opportunity

| Maintained task | Full passes | Causal read counts, repetitions 1/2/3 | Median source recall | Median payload bytes | Median gross input tokens |
| --- | ---: | --- | ---: | ---: | ---: |
| Temporal arguments | 1/3 | inconclusive / 2 / inconclusive | 1.0 | 12,802 | 77,799 |
| Retrieval limits | 1/3 | inconclusive / inconclusive / inconclusive | 1.0 | 25,366 | 98,628 |
| Renderer result contract | 3/3 | 4 / inconclusive / 0 | 0.8 | 21,074 | 86,585 |

Eighteen of 51 causal counts are inconclusive, including six of the nine
maintained attempts. The three maintained medians are therefore unavailable.
Individual positive recovery counts show that missing-context recovery can be
measured, but they cannot substitute for the frozen aggregate decision rule.

That rule needs at least two maintained tasks with three successful repetitions
in both compared arms, a positive comparator sum of complete per-task medians,
and the declared quality/cost/latency gates. Here only one maintained task passes
3/3, and even its causal median is unavailable. No positive eligible aggregate
can be established. Future comparisons must rerun A with the candidate arms in
a fresh matched batch; these historical A-only results cannot be paired with
later B or C results.

## Failure and accounting limits

All 13 disqualified runs have the primary outcome `tool_failure`. Their retained
failure categories overlap: unsupported tool parameters in 11 runs (13 events),
invalid causal parents in three runs, an evidence-span budget exhaustion in one
run, and unverified helper-server identity in one run. The span limit withheld
source and remains a failure even though the agent eventually answered correctly.

The incomplete response total is `imported_heritage-r2`: the model invoked the
built-in resource helper with server `mcp__evaluation`, which is not a configured
server. Codex returned the exact 59-byte host error. That text is retained, but
the frozen reconciler treats a server outside its verified set as inconclusive.
The run's 5,146-byte recorded subtotal must not be promoted to a verified total.
No source was supplied by that error. The raw event and ledger remain available
in the [run artifact](imported_heritage-r2/result.json).

Wrong operation parameters and invalid event IDs are measurement-interface
reliability problems exposed by the run. They do not demonstrate incorrect type
resolution, and the matching answers do not erase the contract failures.
Unproven missing-context chains remain inconclusive even in otherwise passing
runs. No post-hoc relabelling or replacement was used to improve eligibility.

## Costs, latency and graph evidence

- 302 terminal tool calls: 301 evaluation reads and one failed resource helper.
  Of the adapter reads, 298 entered the validated causal trace; three rejected
  attempts are retained separately.
- Recorded response payload subtotal: **353,311 bytes**. The 50 fully reconciled
  runs account for 348,165 bytes; the global verified total is unavailable.
  All nine maintained totals are complete and sum to **184,913 bytes**.
- Verified delivered source occurrences: 77,602 bytes; per-run unique source
  totals 53,128 bytes; repeated delivery contributes 24,474 bytes. Signatures and
  bodies count separately when separately delivered.
- Provider gross input: **2,391,932 tokens**; cached input: 1,684,992 tokens
  (a subset); output: 45,958 tokens (including reasoning). Usage is available for
  all 51 attempts. The separate byte estimate is 19,418 source tokens.
- Overall median end-to-end latency: 27.857 seconds. Maintained nearest-rank p95:
  **59.106 seconds**, using all nine attempts including failures. Cold indexing
  is separate: overall median 0.015 seconds; maintained per-task medians are
  3.940, 3.967 and 5.034 seconds respectively.
- Across repeated task instances, the graph has 15/102 gold dependency links
  available and one delivered. Zero authored forbidden proven relationships
  were observed; this is not an exhaustive semantic-soundness claim. Source
  recall, link availability and delivered links remain separate measurements.

The three maintained tasks come from one repository and concern analysis rather
than code edits. These results do not establish broad coding gains. The requested
unversioned model slug also does not prove fixed backend weights across dates.

## Verification and reproduction

Before freezing, 99 focused checks passed, including v1 artifact preservation,
real source coverage, adapter errors, delivery reconciliation and strict replay.
Seven offline actual-Codex transport modes verified the model-visible structured,
helper and host-error payloads. The batch repeated those probes with its own model
catalog before live requests. Every measured attempt has a fresh source snapshot,
index/store and isolated Codex session, plus effective prompt/tool-schema audit.

The recorded environment uses GPT-5.6 Luna high through Codex 0.154.0 and the
existing ChatGPT login. Production source remains the repaired `9acd3e3` baseline,
extractor 24. No ambient Brain, skills, prior answers, gold or unrestricted source
tools were supplied. Credentials and temporary runtime homes are not artifacts.

From the exploration checkout, replay and reconcile the saved evidence:

```sh
.venv/bin/python benchmarks/results/typescript-context-baseline-v2/verify.py --output benchmarks/results/typescript-context-baseline-v2 --corpus-root benchmarks/corpora/typescript-context-v2
```

Generate the report without running a model:

```sh
.venv/bin/python -m benchmarks.typescript_context_baseline_report --output benchmarks/results/typescript-context-baseline-v2 --corpus-root benchmarks/corpora/typescript-context-v2
```

The [verification record](verification.json) checks all 51 trace replays, unique
identities/sessions, source and harness hashes, effective prompts/tool schemas,
and v2 delivery reconciliation independently of task success. File fingerprints
are retained in [artifact-sha256.json](artifact-sha256.json).

See the [per-case report](report.md), [full summary](summary.json),
[environment](environment.json), [transport probes](transport-verification.json),
[source preflight](preflight.json), and unchanged
[v1 historical evidence](../typescript-context-baseline-v1/README.md).
