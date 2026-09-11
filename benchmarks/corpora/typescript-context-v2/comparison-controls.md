# W2.1.8.1 — Corrected comparison controls

Version `typescript-context-controls-v2`, declared 11 September 2026 before
new measurements. V1 remains frozen historical evidence. The changes and source
requirements are documented in `README.md` and `span-changes.json`. `comparison-controls.json` contains the binding values;
`comparison-controls.sha256` protects that file and its referenced protocol.
These are evaluation requirements. The revised harness must pass its acceptance
checks before new measured runs; declaring v2 does not claim a retrieval gain.

Verify this version with `load_corpus` using this explicit directory, then
`load_controls`. V1 remains the default for its existing replay entry points.

## What changes between the three arms

| Arm | Behavior |
| --- | --- |
| A: current | Search/get and explicit graph retrieval at the repaired baseline revision. No automatic context expansion. |
| B: existing relationships | A plus bounded selection and source hydration using existing validated relationships, including access to file-owned type references relevant to the selected declaration. No new semantic relationships. |
| C: type relationships | B's identical selection, ranking, hydration and limits, with the new proven TypeScript type dependencies and explicit heritage relationships. |

A's production source is pinned to `9acd3e3589ddc034cade36e03c26c4508e9d4434`,
extractor 24. The source corpus checkpoint inherited from v1 is
`da795a6a37e12bcc4acace8498132e6b251c5e19`. V2 corpus/harness commits are recorded with the freeze and run environment.
B and C do not exist yet: pin their
commits, source trees and intended diff before their first measured run. C may
change extraction to supply its declared new relationships. If it needs a
retrieval-policy change, rerun B with that same policy and report the separate
revision; do not attribute a policy change to new semantics.

All arms expose the same logical search, outline, exact source get, graph
neighbors/traversal/paths/retrieve, and bounded file/grep fallback operations.
All operations address only the materialized source snapshot. No external
search, shared index, repository execution, delegation or unlogged source reads.
Read-only shell fallback, if used, must go through the same range/byte/call
accounting as file/grep. An unrestricted shell is not an acceptable measured run.
Do not disable existing graph tools in A to manufacture a weak baseline.
Use source order/ranking unchanged in A, with explicit search limit K=5.
B and C must use the same deterministic ranking and tie-breaks.

## Model, scheduling and source isolation

Use GPT-5.6 Luna, high reasoning, through local `codex exec` 0.154.0 and the
existing ChatGPT login. A non-corpus, no-tool probe succeeded on this account;
its exact command, response and usage are preserved in the JSON. This confirms
the requested route at freeze time, not a dated backend model snapshot or
future quota. No API-key billing or dollar savings is assumed.

Start a fresh, ephemeral session for every task/arm/repetition. The base launch
uses `--ignore-user-config --ephemeral --skip-git-repo-check --sandbox read-only
--json --color never -m gpt-5.6-luna -c model_reasoning_effort=\"high\"` and a
fresh snapshot working directory. Only the evaluation tool adapter is enabled.
The runner must verify the effective instructions and tool list: no Brain,
continuity, user skills, earlier answers, inherited task conversation, gold,
preflight report, or evaluator files may reach the agent. Configuration flags
alone do not establish this isolation. Keep platform-required safety instructions.

Append each unchanged corpus prompt to the common prompt in the JSON. Only the
prompt and saved repository source are agent-visible. Hash the full effective
prompt, tool schemas and configuration in each run record. Preserve raw events,
tool responses, final JSON answer and exact source provenance outside the agent
workspace. Index only source snapshots, never this corpus directory.

Run all 17 tasks three times per arm: 153 runs. Iterate corpus case order; for
each case use arm orders A/B/C, B/C/A, C/A/B across repetitions. Run serially on
the same machine with matched dependency versions and no concurrent benchmark
load. Each run gets a fresh index/store built from the assigned arm. Complete
indexing before timing retrieval; report cold index time separately. Do not
claim model-cache control: record cached tokens, and report gross input tokens
as the primary model-context measure. No resumed sessions or best-of selection.

Use the recorded environment for the first batch. If CLI, dependencies, platform,
model access or effective instructions change, record a new environment block
and rerun the full matched batch; do not mix environments in a paired result.
Record requested model and any provider-returned identity. The unversioned model
slug cannot prove identical weights across dates; state this limitation.

Current retrieval can first be recorded as A alone while B and C are unavailable. When comparing
A/B before C exists, use orders A/B, B/A, A/B for each case's three repetitions
(102 runs). Once C exists, execute the full 153-run matched batch. Preserve
earlier baselines as historical evidence; rerun comparator arms in the matched
batch instead of pairing measurements from different implementation dates.

## Budgets and accounting

The JSON declares common hard maxima. K, anchors, hops, nodes, paths, evidence
bytes and estimated evidence tokens map to existing parameters where available.
Evidence span count, complete serialized output, cumulative source, calls and
wall time are evaluator limits, not claims about existing MCP parameters.
Explicit graph calls and automatic expansion share the same per-operation caps.
Expansion's nested work is recorded, timed and charged; it cannot reset budgets.

Count the complete model-visible UTF-8 result payload, including metadata,
diagnostics and omissions, for tool output: compact JSON for structured results,
and every exact text string for helper or host-error results. Retain each
representation and byte count. Timing/framing is included in provider tokens.
The v2 `read-lineage.md` defines delivery reconciliation and invalid-attribution
accounting separately from the unchanged validated trace. Count every source
byte each time delivered, including fallback and duplicate hydration. Enforce
limits before delivery and return bounded, valid omission/budget metadata;
never cut JSON in the middle or silently drop required evidence. A run exceeding
a hard limit is a failed run, not an inexpensive successful answer.

For measured model tokens, preserve the provider's input, cached input, output
and reasoning fields and their inclusion semantics; do not add a reasoning
subtotal twice. Model-input limits can only be checked at reported usage
boundaries; overshoot is reported as failure, never described as a hard provider
generation cap. Missing usage makes token efficiency unavailable, not zero.
Loci's byte-derived evidence estimate remains labelled **estimated**, separate
from measured tokens. Do not convert ChatGPT usage into an invented dollar cost.

## Fixed decision rule

Report the 14 fixture controls separately from the three maintained Anvil tasks.
Every retained candidate must pass all 42 fixture answers, introduce zero
unsupported proven relationships on any case, and preserve every repaired
endpoint. Candidate ambiguity and unresolved results must remain visible.
Required-context recall counts delivered, hash-matching v2 source spans, not names
or edge identities. Bodies and required export-origin headers are separate
requirements; missing internal source or wrong-file substitutes cannot count. Relationship recall and endpoint availability are separate.

For maintained tasks require at least 8/9 exact answers, and no task may have
fewer successful repetitions than its comparator. For each eligible task take
the median of its three avoidable-read counts, then sum those medians. Eligibility
requires all three repetitions of both arms to succeed, as specified below. Require at
least a 20% reduction in that sum and at least one fewer avoidable read on two
of the three tasks. The comparator sum must be positive; zero offers no
demonstrable read-reduction opportunity. Classify avoidable reads only using
the original explicit causal rules with the v2 source spans and separately
retained invalid attempts; mere time proximity
is insufficient. Deliberate hydration, setup and necessary verification do not
become avoidable reads. All their cost still counts.

Require no reduction in each task's median delivered-context recall, no increase
in the sum of per-task median complete tool-output bytes or gross model input
tokens, and maintained-task p95 end-to-end latency at most 1.25 times the
comparator. Use nearest-rank p95 over all nine maintained runs, including capped
timeouts. Report all raw counts, per-case outcomes and medians; nine observations
are descriptive evidence, not statistical significance or broad coding gains.

Evaluate B against A. Evaluate C against both B and A: correctness and cost/latency
nonregression must hold against both; incremental read improvement must meet the
same rule against B. If B was rejected, C can be a final candidate by meeting the
whole rule against A, but a separate benefit from new semantics remains unproven
unless the C-versus-B rule also passes. No threshold change after seeing results.

Timeouts, malformed answers, exhausted budgets and arm failures remain in the
denominator. A task with failed answers cannot satisfy an efficiency improvement
by stopping early: compare read improvement only where all three repetitions
of both arms succeeded, and require at least two such maintained tasks; quality
and latency still use all nine. The context-recall and total-cost checks use all
three tasks, including failed attempts. A confirmed provider/host outage is an invalid
attempt, logged separately; allow at most one replacement of the entire paired
three-arm block for that case/repetition. Preserve the original attempt. A second
outage leaves the batch incomplete, with no acceptance claim. No correctness retry.

Missing evidence, inconsistent source/configuration, or unavailable token/lineage
accounting yields **inconclusive**, never a pass. Preserve negative results. Any
changed corpus, gold, limits, model or thresholds requires a newly named protocol
before new measurements, with the old protocol and results retained.

Official runtime reference: [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
documents JSON events, usage and reuse of saved authentication. Account access is
supported separately by the recorded local probe.
