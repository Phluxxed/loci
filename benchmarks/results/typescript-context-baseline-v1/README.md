# W2.1.7 — Recorded A-only baseline

The 51 planned attempts are complete. **This is historical baseline evidence,
with inconclusive read-efficiency accounting—not an accepted improvement or a
usable read-reduction comparator.** Preserve these results and correct the
protocol before a new matched comparison. Production retrieval, corpus, gold,
controls and measurement harness stayed fixed throughout the measured batch.

| Group | Fully passing runs | Oracle-matching answers, ignoring run failures |
| --- | ---: | ---: |
| 14 fixture cases × 3 | 28/42 | 33/42 |
| 3 maintained Anvil tasks × 3 | 4/9 | 8/9 |
| Total | 32/51 | 41/51 |

A fully passing run requires a correct answer and a completed, budget-compliant,
accounted execution. Eight completed attempts differed from the oracle; eight
ended as tool failures and three as budget failures. Two tool-failed attempts
also had non-matching answers. These categories explain why 41 matching answers
do not mean 41 passing runs. There were no timeouts or replacement attempts.

## What the experiment established

- All 51 recorded traces replay exactly. There are 51 distinct trace sessions
  and provider sessions. Effective prompts, Luna/high settings, source manifests,
  environment and core harness hashes verify against the freeze. Canonical tool
  schemas match across all requests. Endpoint preflight found all 55 expected
  symbols; 14 other required spans are source-only evidence.
- Provider usage is available for every run: **2,463,293 gross input tokens**,
  including 1,739,776 cached input tokens, and 47,634 output tokens. Output
  includes reasoning; cached input is a subset of gross input. These are ChatGPT
  usage observations, not an API bill or dollar-saving estimate.
- Recorded source delivery is **65,660 bytes**, including 12,998 repeated bytes.
  The recorded JSON subtotal is **319,486 bytes**. Complete JSON accounting is
  unavailable in ten runs because some MCP error/resource-helper responses were
  outside the adapter trace. Their reported provider usage remains included.
- Median end-to-end time is 30.66 seconds. Maintained-task nearest-rank p95 is
  **110.23 seconds**, over all nine attempts including failures. Cold indexing
  is separate. No timeout was replaced by a cheap successful answer.
- Forty-seven runs have inconclusive avoidable-read accounting. The remaining
  four recorded counts are zero; **all nine maintained runs are inconclusive**.
  There is no demonstrated positive comparator opportunity for the frozen
  read-reduction decision rule.

## Interpretation limits exposed by the baseline

**Full-span scoring confounds useful context with wrappers and whitespace.**
For `anvil_temporal_arguments-r1`, the five required spans total 835 bytes and
816 of those bytes were delivered. The remaining 19 bytes are two `export `
prefixes and five trailing newlines. Full-span recall is nevertheless zero.
The answer is correct. Across maintained runs the median complete-span recall
is zero; this must not be described as zero useful context delivered. The same
full-span requirement prevents many missing-context chains from proving a
completed recovery. These are the frozen scores, retained without adjustment.

**The call-control question is ambiguous.** The four endpoint-control cases
ask for `argument_type` “for the existing call”; their oracle expects the
callee's declared parameter type, `unknown`. Nine of their twelve answers
instead report `number`. That is a plausible call-site reading of this wording.
The strict oracle differences remain failures, but cannot alone establish a
retrieval defect or regression in the repaired endpoints. One other mismatch,
`anvil_retrieval_limits-r1`, included the `problem` message key beyond the four
keys expected by the authored answer.

**Lineage errors and budget failures have measurable costs.** Examples include
prose where `because` requires an exact event ID, selection provenance attached
to an explicitly non-selection read, and broad grep output exceeding the
64-span ceiling. Four attempts triggered the span limit. One also requested
output beyond the per-operation/cumulative JSON allowance. Eleven unaccounted
MCP responses occur across ten runs; two are empty Codex resource-list helper
responses. These failures are preserved, not repaired after observing answers.

**Graph availability and agent use are different measurements.** Across repeated
cases, 15 of 105 authored semantic-dependency instances have direct matching
baseline edges; zero such edges were delivered in agent graph packets. Agents
made 126 search, 67 get, 66 grep, 46 file, 21 outline, four graph-anchor and one
graph-import calls, plus two empty resource-list calls. They never requested
paths or graph traversal. The zero delivered-link score therefore does not
establish that explicit graph retrieval cannot return existing edges. Separate
`explicit-graph-probes.json` uses evaluator-selected gold endpoints to record
that capability: all 35 declared relationships across 17 cases were probed;
five returned paths, with no errors or skipped endpoints. These probes are
outside the 51 blind agent measurements and all their cost/quality totals. Zero authored forbidden proven relationships were observed;
this is a bounded negative check, not exhaustive semantic soundness.

## Reproduce and inspect

- [Aggregate report](report.md) and [complete machine-readable summary](summary.json)
  retain every case outcome, median, null, failure and raw result.
- [Integrity verification](verification.json) records the 51 replays, model/tool
  checks, group counts, triggered limits and exact answer differences.
- Each case/repetition directory contains `request-audit.json`, `provenance.json`,
  `adapter-trace.json`, `events.jsonl`, `stderr.txt` and `result.json`.
- Core harness commit: `310caddedbf085ed28f395b0cc799bbd164c75a6`.
  Production engine: `9acd3e3589ddc034cade36e03c26c4508e9d4434`, extractor 24.
  The report is postprocessing; the environment file fingerprints the actual
  five measurement/scoring modules used throughout the run.
- Run `.venv/bin/python -m benchmarks.typescript_context_baseline_report --output
  benchmarks/results/typescript-context-baseline-v1` to regenerate aggregates.
  Use the standalone `verify.py` and `graph-probe.py` through `runpy.run_path`
  from the checkout, as described by their imports and the runner guide.

The requested model was GPT-5.6 Luna/high via Codex CLI 0.154.0 and existing
ChatGPT authentication. An unversioned model slug does not prove fixed backend
weights. Earlier baselines cannot substitute for rerunning A alongside future
B/C arms. Any correction to questions, gold-span policy, tool/error accounting
or the comparison contract must be declared before another measured batch;
retain this version and its failures. The historical 38% figure is not revived.

Offline integrity replay from the checkout:

```sh
.venv/bin/python -c 'import runpy; runpy.run_path("benchmarks/results/typescript-context-baseline-v1/verify.py", run_name="__main__")'
```

For a new direct capability probe, preserve the original and choose a new output:

```sh
.venv/bin/python -c 'import runpy,sys; sys.argv=["graph-probe.py","--output","/tmp/loci-graph-probes-new.json"]; runpy.run_path("benchmarks/results/typescript-context-baseline-v1/graph-probe.py",run_name="__main__")'
```
