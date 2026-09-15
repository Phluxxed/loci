# Complete-work graph-value pilot

This is the completed design for **W1.8.4.4.10.2.1**, not a campaign freeze or
an experiment result. Harness/accounting implementation is .10.2.2; validated
publication is .10.2.3; measured execution is .10.2.4. The design answers Vik's
15 September question about whether richer graph context pays for itself
through less later retrieval, fewer mistakes and better follow-on work.

> **TL;DR:** Compare graph-on/off across the whole useful task, including follow-ups; judge correct completion before efficiency.

## Question and controlled difference

The primary question is: **for these tasks, does enabling graph enrichment
throughout the workflow improve correct completion or its total time and cost,
including the downstream work after initial orientation?**

The treatment is fixed for the entire episode. Graph-on uses normal deterministic
retrieval. Graph-off preserves the same anchor selection, source lookup/paging,
tool names, discovery, instructions and allowed shell navigation, while omitting
graph traversal and graph-derived enrichment. It is an experiment-controlled
intervention, never an agent-selected graph option or a new public product knob.
The control must preserve ordinary anchor source quality: it cannot manufacture
a benefit by truncating direct source or disabling a useful non-graph lookup.
Differences in graph-related source and proof are the intended intervention.
Assignment does not force Loci invocation or guarantee a graph edge. Retain
non-use and empty graph results in the assigned arm; report invocation/delivery
separately. Do not select only episodes that received graph evidence.
The exact control implementation and truthful output accounting are verified
before freeze; a matched control is not claimed to exist yet.

Later-call and rework differences estimate the effect of the **assigned whole
workflow**. They do not isolate reuse of the first packet: later retrievals also
differ. Stage boundaries localize savings descriptively. Graph delivery is not
proof of internal reliance. A first-stage-only treatment would answer a different
question under a hybrid workflow and is not an additional selected campaign.

## Two concrete episode types

The exact prompts and behavioral acceptance are in [episodes.json](./episodes.json).
Candidates preserve the source grounding and primary adaptations separately.

| Episode | Orientation | Useful change | Related continuation |
| --- | --- | --- | --- |
| `anvil-creation-evidence` | Explain creation-phase evidence and its display-only boundary | Distinguish explicit details, Git history and unproven origins in task detail | Verify API/embedded-page parity and safe output for the same evidence |
| `loci-direnv-exclusion` | Trace exclusion policy through scanning and incremental replacement | Exclude exact `.direnv` directory components with policy tests | Exercise moved source and surviving siblings through real incremental indexing |

Anvil uses the retained 638-file source tree whose hash map is recorded in the
original `ordinary-adoption-v1/cases.json`, originally exported from commit
`53bf29e60cece2335aa39fe301935a07e8e8d4e4`. The current readable copy is
`/tmp/anvil-source-tasks-20260914/t21`; an absent original archive or Git history
must not be invented. Freeze a new verified export from that exact file map.
The feature's Git-history fixtures create their own temporary repositories.

Loci uses a clean export of commit
`f3d9134aece5156bec1dcc302d4330522d1d96e5`. Pin the navigation server separately
from the target checkout: benchmark edits must not modify the tool serving it.
The protocol, rubric, candidates, evaluation artifacts and other arm's work are
outside the agent's accessible workspace. Freeze the exact target export and
any benchmark/history exclusions consistently in both arms; preserve all product
source, applicable instructions and selected test dependencies.

These two repository tasks span cross-file TypeScript presentation and Python
index maintenance. They are a bounded pilot, not a representative sample of all
languages, repositories or ordinary engineering work.

## Matched schedule and context

Run **eight episodes: two types × two repetitions × two arms**. One episode has
three sequential user turns in the **same native agent/session**, without a
context reset, summary substitution or child delegation. Each episode starts
with a fresh Terra/high agent, fork-none. Do not reuse an agent across episodes.
All three prompts are condition-independent; future prompts are not shown early.
Submit the next fixed prompt after the preceding turn ends normally, even if
its answer or patch is incorrect. No reviewer hints or outcome-based nudges.

| Block | Type | Repetition | Sequential arm order |
| --- | --- | ---: | --- |
| 1 | Anvil | 1 | on, off |
| 2 | Loci | 1 | off, on |
| 3 | Anvil | 2 | off, on |
| 4 | Loci | 2 | on, off |

This counterbalances order for each task while keeping the first campaign
small. Four matched pairs reveal repeat-to-repeat and task-type reversals;
they do not justify population estimates or significance claims. Run one measured
episode at a time to avoid deliberate concurrent contention. Independent review
is outside measured context and uses Sol/high. No Astra experiment workers.

Every episode gets an isolated writable repository and test store, with identical
starting source identity within a task. Never share patches, generated files,
test outcomes, index mutations or answers across arms. Install equivalent pinned
dependencies and pre-index the clean sources before timing. Both arms start with
ready indexes and empty per-episode continuation-reference state. This measures
an indexed working repository, not cold installation/indexing cost; report that
setup separately. Identical logical workspace paths are preferred inside isolated
environments. Otherwise freeze equivalent path shapes and account for path tokens.

Provider prefix caches cannot be assumed empty or controllable. Record actual
cached/uncached usage and runtime identity, retain order, and document inherited
host instruction differences. Source-cache readiness and provider-cache hits are
different facts. Unmatched host configuration or unintended graph leakage makes
the affected causal comparison unproven; its outcome is retained.

## Boundaries, stopping and failures

The fixed stage caps are **120 seconds orientation, 360 seconds implementation,
and 240 seconds continuation**, at most **720 seconds per episode**. Eight
episodes therefore have a maximum 96 minutes of measured execution; preparation
and independent evaluation are separate. These are resource/stopping limits,
not quality or performance targets. The preflight must establish that the
controller can enforce the boundary and retain partial usage; failure to do so
blocks launch rather than silently changing this design.

Measure episode latency from first prompt submission through final completion,
including tool time and normal stage handoff. Automate handoff promptly; record
controller delay separately. Report stage elapsed and complete wall time. A
delayed operator must not selectively improve either arm's reported latency.

A stage timeout, native abort or unrecoverable harness failure ends the episode;
later stages are `not_reached`. A recoverable tool error or failed local test
does not stop it: ordinary agent retries/repairs within the cap are part of the
measured work. There are no new replacement episodes or operator repair prompts.
Wrong early understanding can be corrected later; it is recorded as an error
and possible rework, rather than automatically invalidating correct finished work.

Editing source during the read-only orientation or accessing hidden future
prompts/evaluator material is a protocol violation and an unsuccessful retained
episode; later repair does not erase it. Ordinary navigation choices, including
not invoking Loci, are not protocol violations.

Retain every scheduled row. An aborted or incorrect episode is unsuccessful and
its consumed time/tokens remain in aggregate numerators. Missing telemetry is
unknown, never zero. A fixture/setup/control defect is an invalid comparison,
not evidence that one graph policy is worse. Report observed failure and reason,
do not remove the row or rerun it into this campaign. A later justified campaign
needs its own Task and new freeze.

## Correctness and rework

Primary success is the final artifact satisfying **all requested terminal
behavior and preserved invariants** within the cap. Stage-level correctness is
reported separately, including errors that were fixed. An early explanation
error that is explicitly corrected and does not survive in the final artifact
does not erase successful completion. A material unresolved final claim does.
Do not score incidental symbol-name mentions as if they were product behavior.

Freeze independent evaluator fixtures and expectations before launch. They must
exercise the requested behavior through existing public seams and include the
negative cases in `episodes.json`, not merely run tests written by the agent.
Agent-authored tests are part of the deliverable but are not the sole oracle.
Keep the evaluator and its expected results inaccessible to trial agents. Run
oracle checks against retained stage/final snapshots outside measured agent
time, with identical resources. Agent-run tests remain inside measured time.

An arm-blinded Sol reviewer checks final claims, changed scope, preservation of
invariants and whether the requested tests actually exercise the behavior.
Review artifacts identify source and output hashes; primary owns disposition.
`severe_failure` means a prohibited outside-workspace operation, alteration of
protected evaluation/control data, or the episode's specified material invariant
violation. Ordinary failed tests are not severe by themselves. Severity is
assigned using frozen rules, never to favor the faster result.

Rework is diagnostic: retain failed test commands, corrective patch cycles and
source-backed mistaken claims later corrected. Label uncertain attribution;
repeated commands alone do not prove a mistake. No additional repair turns are
injected to make either arm succeed.

## Whole-episode accounting

Retain each stage's native thread/turn identity, exact prompt attestation/hash,
first/last event boundaries, outcome, patch/snapshot identity and provider usage.
Link all three turns explicitly. Sum incremental per-request usage exactly once;
do not sum cumulative session snapshots again at every follow-up. Validate a
multi-turn control before launch. Count unsuccessful requests and retries.

Report by stage, episode, arm and matched pair:

- Correct completion, stage outcomes, material errors, severe failures and rework.
- Whole/stage wall time and controller delay.
- Uncached input `U`, cached input `K`, output `O`, and gross input `U + K`.
- MCP and shell operations separately, outer tool rounds, and model requests.
- Visible packet bytes, source-content bytes, graph proof delivered, and
  repeated reads of unchanged source spans. Changed-source reads are not duplicates.
- Downstream (implementation + continuation) totals alongside orientation totals.

Earlier source validation rereads the target's final files. That is insufficient
once agents edit source. Preserve the content-addressed source version relevant
to each retrieval and subsequent index refresh; a legitimate edit must not be
reported as corrupt initial source. Source freshness/proof and arm identity must
remain auditable throughout the episode. Keep input snapshots and final diffs.

The old collectors remain unchanged. An episode adapter may reuse their per-turn
results; version any new boundary, usage or source-history accounting. This is
bounded benchmark support, not a new product telemetry system.

## Predeclared decision rule

There is no new arbitrary gross-input ceiling. Report every pair and task type
before aggregation. For each arm let `S` be correct terminal completions and let
totals include **every scheduled episode**, including unsuccessful ones:

`time_per_correct = total_elapsed / S`

`C(alpha, beta) = total_U + alpha * total_K + beta * total_O`

`normalized_cost_per_correct = C(alpha, beta) / S`

When `S = 0`, both per-correct measures are infinite, and two zero-success arms
have no efficiency winner. This prevents cheap, incomplete answers from winning
by being omitted. Also show total consumed resources and success counts: ratios
per success must not conceal a task-type regression or an individual failed pair.

The observation surface does not provide verified billing rates for the selected
native worker model. Therefore this design claims no billed dollars. Freeze the
normalized sensitivity region **0 ≤ alpha ≤ 1, 1 ≤ beta ≤ 10**, relative to one
uncached input token. It spans free-to-full-price cached input and output priced
one-to-ten times input; it is a declared analytical range, not an assertion
about provider tariffs. Publish the break-even line and direction at all four
corners. The cost difference is affine, so the corners establish its sign across
the rectangle. Actual verified rates, if available before campaign freeze, may
be reported additionally; they do not replace the predeclared sensitivity.

Use **zero-tolerance observed Pareto dominance** for the pilot because no
business-valued tradeoff or justified noise allowance has been supplied:

1. An arm must have no fewer correct completions for either task type and no
   additional severe failures of any frozen category.
2. Its elapsed per correct completion and normalized cost per correct completion
   must be no worse overall **and for each task type** throughout the declared
   rate region. If a task type has zero successes in both arms, its efficiency
   comparison is unproven and no overall dominance is declared.
3. It must improve at least one of correct completions, elapsed per correct, or
   normalized cost per correct. A cost-only improvement must hold strictly
   throughout the rate region. Apply the same rule symmetrically to graph-off.
4. Otherwise report **mixed/inconclusive**, showing useful quality/time signals
   and exactly which prices or task types reverse the cost comparison. A mixed
   result is not proof of no benefit. Missing required evidence yields **unproven**.

These classifications describe the observed pilot only. Report effect sizes even
for a dominance result; tiny differences are not declared practically material
or statistically reliable. A quality improvement with a cost/time tradeoff stays
visible rather than being flattened into a token failure. Do not invent a larger
experiment merely to obtain a preferred verdict.

The old binding campaigns' 1.25 gross-input, elapsed and output-byte gates and
fact scores remain valid historical results. This is a **prospectively different
unit of work and decision rule**, selected to answer downstream-inclusive value.
It does not retroactively pass those campaigns. Neither pilot dominance nor a
completed negative investigation supplies full-workload or Objective acceptance.

## Required handoff and claim limits

W1.8.4.4.10.2.2 must make the matched control, multi-turn capture, isolated source
history, dependency environment and independent oracles concrete. .10.2.3 must
validate and freeze them. This design's source references are checked by reading,
not by running a patch or claiming a passing evaluator. Before launch, both
baseline tasks must have working dependencies and evaluators must reject an
unchanged implementation where a change is requested. Do not tune prompts,
caps or metrics using measured arm outcomes.

The useful outcome is an honest benefit, harm, mixed or unproven result for these
four pairs, including what happened after orientation. No claim of initial-packet
causality, inner-model reliance, population significance, cold-start cost,
verified billing or general multilingual acceptance is licensed by this pilot.

> **TL;DR:** Eight episodes, fixed whole-workflow treatment, preserved follow-up context, behavioral correctness first, failures included, and explicit cost/causal limits.
