# R1 real-source pilot complete: hold advancement

All 16 scheduled native Codex attempts are retained, using `gpt-6.1-terra` at
`max` effort. The frozen grader passed 15; independent archive replay reproduced
every outcome. One attempt ended during mandatory catalog capture without a task
answer. Its failure and known costs remain recorded, its treatment observation
is unqualified, and it was not replaced.

**Recommendation: keep R1 experimental and hold advancement.** The integrated
implementation remains deterministically qualified, but this pilot demonstrates
no benefit from its optional semantics or proof. None of the four integrated
sessions invoked any Loci tool; three completed their engineering tasks using
native tools, and one never reached the task. This does not establish a general
adoption defect or justify rejecting the architecture. It does not justify
production integration or further architecture expansion either. Stop this
bounded evaluation here.

The [sanitized machine evidence](real-repo-pilot-checks.json) records all 16
observations, separate review judgments, usage, operational checks and hashes of
the private evidence. Detailed source, prompts, oracles, catalogs, native traces,
candidate changes and independent reproductions remain local and ignored.

## Correctness before efficiency

The source pool was the prospectively frozen, maintained repository snapshot:
701 files and 10,062,803 bytes. Four engineering tasks were fixed before measured
execution: T1 shared-helper location, T2 a cross-file JavaScript contract,
T3 uncertainty in a reusable Python template, and T4 a bounded BOM reader change.
Three tasks use Python, whose semantic analysis is unsupported by integrated R1.
The JavaScript task was the single supported semantic opportunity.

The separate reviewer received condition-hidden tasks, original source and
candidate artifacts, without official scores, usage, native traces or scorers.
All 16 judgments are retained by packet hash; no incidental unblinding was
reported. The reviewer accepted all 11 submitted investigation answers and the
integrated condition's code change. No answer existed for the failed capture.

The other three code changes pass the frozen behavior checks but miss an explicit
append requirement: a valid BOM-prefixed TSV without a trailing newline is
accepted by their reader, then becomes corrupt when a row is appended. The
defect pre-existed in ordinary append handling; it is not a new regression.
However, the task explicitly required appending to a valid BOM-prefixed file to
work. The frozen oracle checked terminated files and missed this boundary.
Independent synthetic reproductions confirm the gap. The integrated candidate's
append change handles it, but that session used no Loci tools.

Frozen grades remain unchanged. These post-run review findings qualify task
completion; they are not substituted into the prospective score or used to tune
the candidate, task, scorer or prompts.

| Task | Condition | Frozen / independent review | Execution s | Input tokens | Cached input | Output tokens | Total tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| T1 | native | pass / pass | 67.2 | 236,336 | 199,424 | 7,105 | 243,441 |
| T1 | path-only | pass / pass | 93.9 | 521,547 | 441,344 | 8,385 | 529,932 |
| T1 | integrated | pass / pass | 79.2 | 270,908 | 244,480 | 8,036 | 278,944 |
| T1 | eager | pass / pass | 130.9 | 351,114 | 319,744 | 8,329 | 359,443 |
| T2 | native | pass / pass | 101.9 | 343,075 | 300,672 | 11,049 | 354,124 |
| T2 | path-only | pass / pass | 75.7 | 234,169 | 207,488 | 8,133 | 242,302 |
| T2 | integrated | pass / pass | 95.8 | 279,137 | 249,088 | 10,710 | 289,847 |
| T2 | eager | pass / pass | 143.7 | 354,996 | 316,160 | 9,911 | 364,907 |
| T3 | native | pass / pass | 78.3 | 266,888 | 222,720 | 7,812 | 274,700 |
| T3 | path-only | pass / pass | 90.1 | 271,111 | 225,920 | 7,895 | 279,006 |
| T3 | integrated | fail / no answer* | 26.6 | 51,683 | 24,576 | 2,590 | 54,273 |
| T3 | eager | pass / pass | 107.2 | 353,584 | 307,072 | 9,195 | 362,779 |
| T4 | native | pass / append defect | 103.5 | 412,520 | 383,488 | 9,157 | 421,677 |
| T4 | path-only | pass / append defect | 100.1 | 414,858 | 385,280 | 8,672 | 423,530 |
| T4 | integrated | pass / pass | 111.7 | 390,720 | 358,272 | 9,695 | 400,415 |
| T4 | eager | pass / append defect | 86.2 | 312,895 | 282,368 | 7,483 | 320,378 |

*T3 integrated is excluded from controlled condition comparisons. It contains a
real failed capture and no task result, not a fast completion or a demonstrated
Loci failure. Total tokens equal input plus output; cached input is already part
of input. Reasoning tokens are part of output and are retained separately in the
machine evidence. These are provider-reported usage observations, not billing or
complete upstream-request counts.

## Acquisition and execution effort

Only T1 and T2 have four treatment-qualified successes accepted by both the
frozen evaluator and independent review. The following sums describe those two
tasks only; they do not estimate a population treatment effect.

| Condition | Execution s | Total tokens | Uncached input | Task outer calls | Shell operations | Loci calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native | 169.0 | 597,565 | 79,315 | 12 | 24 | 0 |
| path-only | 169.6 | 772,234 | 106,884 | 18 | 19 | 5 |
| integrated | 175.0 | 568,791 | 56,477 | 11 | 23 | 0 |
| eager | 274.6 | 724,350 | 70,206 | 16 | 22 | 2 |

Task outer calls exclude the mandatory catalog capture and its parse-failed
attempt. Nested shell and MCP operations are different units and must not be
added to outer calls. Shell counts include catalog readback. Integrated's lower
token count here cannot be attributed to a tool it never invoked. Path-only's
faster T2 also used no Loci. Each cell is one observation, with substantial input
caching and no repeated condition estimate.

Three concrete acquisition episodes explain the observed use:

- **T1 path-only:** two retrievals and three exact-source continuations delivered
  19,849 source-content bytes, followed by native line-numbered reads for the
  answer. Discovery and paging added model/tool turns. The answer was correct,
  but this run took 93.9 s and 529,932 tokens versus native's 67.2 s and 243,441.
- **T1 eager:** one retrieval delivered archived/adapter source and three
  embedded relationships. The agent then inspected the requested shared helper
  with native tools. It completed correctly in 130.9 s. Independent replay found
  one relationship marked complete lacked 570 bytes of required caller support
  even across its whole delivered packet. The archived relationship is supported;
  this is a delivery/completeness defect, not evidence of a false relationship.
- **T2 eager:** one retrieval returned Python test/validator source with four
  supported relationships, rather than the requested JavaScript route sources.
  Native search and direct source reads supplied the final contract answer.
  Completion took 143.7 s, compared with native's 101.9 s. The recorded sequence
  supports a retrieval detour; it does not isolate how much time the detour caused.

Across all 16 sessions there were seven Loci calls in three sessions: four
retrievals and three reads. No semantic or focused-proof endpoint was called.
All 24 delivered source spans and three continuation links independently
verified. Six of seven embedded eager relationships had complete delivered
support under the existing strict check. Eager reference semantics differ from
the experimental native semantic implementation; embedded delivery is not an
integrated semantic/proof request.

The tool outputs contained 28,452 source-content bytes including overlap;
per-packet evidence accounting totaled 27,626 bytes. Neither is unique model
context. Native shell-output bytes mix source, command metadata and validation;
exact acquisition-only time, total native source bytes and exhaustive repeated
reading are unknown. Two identical shell-command repetitions were observed in
the code-change runs; repetition alone does not establish waste. The common
source-only snapshots also caused routine Git-status failures because they were
not Git checkouts. All failed operations remain counted.

## Timing, qualification and recovery

The table measures original native process launch-to-exit, including startup,
mandatory capture, task work and verification performed by that agent. It
excludes separate preflight, offline grading/replay and operator repair pauses.
Full time through independently accepted completion was not instrumented.

The 16 process durations sum to **24 min 52 s**. The first native task started
at 09:40:00.861 AEST and the final task closed at 11:36:48.391 AEST on October 28:
**1 h 56 min 48 s** including inter-run preparation, interruptions and repairs.
That operational span is separate from task execution and excludes earlier
preflights/cohorts and final review. The measurement workflow imposed substantial
real overhead that must not be hidden by the per-task times.

Four separate operational probes passed before scoring, exercising every
assigned endpoint. Their unscored execution costs were native 20.0 s / 52,757
tokens, path-only 83.3 s / 270,386, integrated 76.9 s / 360,732, and eager 84.2 s /
287,067. Task-level tool use remained voluntary. Fifteen measured catalogs were
verified against the qualified context; the failed capture remains unqualified.

Three reader recoveries preserved original sessions and costs. T2 integrated
first submitted a non-executing syntax typo, then successfully ran the exact
capture. T2 native differed only in a typed memory-summary truncation count;
visible instructions and catalogs matched. T3 integrated submitted a different
SHA constant, failed capture, and stopped without an answer. That last attempt
was recorded as incorrect/unqualified and the remaining independent assignments
continued. The waiting normal-Terminal runner accepted the bound repair without
another user relaunch. No native task was rerun.

Instrumentation changes are explicit, retained amendments; the source/tasks,
task prompts, evaluators, model/effort, condition order and native protections
remain bound to the original freeze. Raw rendering variations are retained.
Personal-host observations do not prove equality of unseen external memory
files. Original failed indices and archives remain preserved.

Independent replay verified 16 distinct native sessions, known reported usage,
source changes, task bindings and frozen oracle outcomes with zero substantive
disagreements. Three raw stderr differences were replay-root paths only. All
46,195 protected evidence files were unchanged. The latest runtime repair passed
214 focused checks; this closeout adds no runtime changes or further model runs.

## Decision and retained deliverables

The [experimental interface](../../docs/r1-integrated.md) supplies retrieval,
exact reads, optional JS/TS/Rust semantics and focused proof, while source-only
operations avoid semantic construction. [Deterministic qualification](qualification.md)
retains 288 independently replayed fixture executions with zero integrity
failures or forbidden proven claims. Its bounded source coverage and cost limits
still apply; Python/Go semantics remain unsupported.

The implementation and bounded pilot are complete. There is no remaining launch
blocker. The unresolved question is usefulness of optional semantics: this pilot
did not exercise it during task work. The supported conclusion is insufficient
evidence to advance, not proof that the architecture cannot help. The observed
eager detours, delivery gap, and missed append boundary are retained findings,
not authorization for new product changes or another campaign.

Private retained evidence is under
`real-repo-pilot/execution-capture-v2/analysis/`: `metrics.json`/`metrics.csv`,
`comparison.json`, `command-index.json`, `tool-attribution.json`,
`independent-replay/final16-review.json`, and `blinded-review/final-16.json` with
the synthetic reproductions. `closeout.py` checks packet hashes and projects
only selected metrics into the public machine evidence. Its input hashes are
recorded in `closeout-inputs.json`. Raw private source and execution artifacts
were not published. Earlier toy cohorts remain separate historical evidence.
