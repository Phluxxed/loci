# Routing qualification follow-up decision

The repaired routing-v2 qualification remains **rejected**. The next useful
work is a bounded answer-reliability diagnostic with source delivery held fixed.
There is no demonstrated retrieval defect to repair from the remaining failure.
This decision selects and limits that diagnostic; it does not start provider
measurement or replace the completed qualification.

## Evidence and diagnosis

The [published assessment](https://github.com/Phluxxed/loci/blob/38565489e1c99d003b8d35c7bb3e371495411be8/benchmarks/results/typescript-context-routing-v2/interpretation.md)
retains 102 independently replayed attempts, 9/9 successful initial maintained
source deliveries, and 12/14 passing numerical gates. Candidate fixture passes
are 41/42; generic-shadow success is A 3/3 and B 2/3. Both failed gates arise
from the same answer. The measured maintained-task savings remain evidence,
but cannot override those failures.

The failed [generic-shadow result](https://github.com/Phluxxed/loci/blob/38565489e1c99d003b8d35c7bb3e371495411be8/benchmarks/results/typescript-context-routing-v2/generic_shadow-r1-B/result.json)
contains four successful calls: exploration, search, exact get, and a file
read. The complete identity function, its import, and the imported interface
were delivered. The answer correctly identifies a local generic and says the
imported fields are not required, but incorrectly denies both number and string
round trips. Required-source recall is 1.0; there are no forbidden proven
relationships, delivery-integrity violations or tool failures in this attempt.

The [effective task](https://github.com/Phluxxed/loci/blob/38565489e1c99d003b8d35c7bb3e371495411be8/benchmarks/results/typescript-context-routing-v2/generic_shadow-r1-B/request-audit.json)
asks whether local `Payload` refers to the imported interface, and requests
`parameter_kind`, `requires_imported_fields`, `number_round_trip`, and
`string_round_trip`. The supplied `processOrder<Payload>(value: Payload): Payload`
returns `value` unchanged. The existing
[strict TypeScript control](https://github.com/Phluxxed/loci/blob/38565489e1c99d003b8d35c7bb3e371495411be8/docs/reviews/2026-09-10-typescript-context-gaps.md)
already verifies number/string calls independently of the imported interface.
There is no substantiated alternative answer or scorer defect that warrants
rescoring the failed attempt.

The exploration result reports `partial`, `anchor_limit`, and two
`unresolved_relation` omissions while returning the complete function. Those
are possible context cues to investigate, not proven causes. Later exact reads
also supplied the relevant source. The recorded model output does not explain
the two boolean choices; five correct sibling attempts do not identify their
cause or establish that routing preserves answer reliability.

## Selected diagnostic

Prepare one separately versioned diagnostic, with **48 fresh answer attempts**:
four conditions with twelve repetitions each. Use the original generic-shadow
question and answer oracle, the pinned source, and GPT-5.6 Luna at high reasoning
effort through the same available Codex/ChatGPT route. No new retrieval feature,
answer-verification prompt, model change, gold hint or correctness retry is part
of this diagnostic.

| Condition | Routing prefix | Evidence presentation |
|---|---|---|
| D0 | Absent | Four retained tool-result payloads |
| D1 | Exact published prefix | Same four retained tool-result payloads |
| D2 | Absent | Exact source spans from those payloads |
| D3 | Exact published prefix | Same exact source spans |

The common diagnostic instruction says that retrieval is complete, all evidence
is supplied, and the agent must answer the unchanged question from it. Disable
additional repository tools for every condition. Preserve the routing prefix
verbatim in D1/D3. This isolates its residual effect on source comprehension;
it does **not** exercise its effect on live retrieval choices.

For D0/D1, supply all four successful payloads from the failed attempt in their
recorded order. Do not include the previous answer, gold, verdict, model
reasoning, or a narrative explaining generic shadowing. For D2/D3, supply each
validated source span in the same event order, retaining repeated spans,
filenames and source bounds. Remove navigation metadata and JSON packaging;
do not remove source, omit the imported-interface distractor, deduplicate spans,
add source, or introduce semantic explanations. Preflight must verify equal
source content, order and multiplicity between the presentations.

This is a comparison of presentation bundles. If it finds a difference, it
cannot attribute that difference specifically to `partial`, an omission label,
JSON syntax, response length, or another individual metadata field. Supplied
evidence in a fresh prompt also cannot reconstruct the original model's hidden
state or prove why the historical answer failed.

Run serially in twelve blocks containing all four conditions, rotating the
condition order by one position per block. Freeze the exact prompts, packet
transformation, source proof, model/host controls, budgets, schedule, scorer and
report rules before any provider outcome. The preflight must establish current
model/host availability and capture the effective request. If a required
capability is unavailable, report that blocker; do not silently substitute a
different model or transport.

Retain every scheduled attempt, raw request/output, identity, failure, usage and
latency. Cached input remains part of gross input. An interrupted or failed
attempt is not replaced; an interrupted campaign may resume only untouched
scheduled identities after freeze validation. Stop after the declared 48 slots;
no adaptive extension, selective replay, majority-vote replacement or automatic
full-workflow comparison follows.

## Interpretation and stopping rules

Publish per-condition and per-field correctness counts, invalid/missing-answer
counts, full output patterns, costs and uncertainty. Twelve observations per
condition supply a bounded diagnostic, not a powered noninferiority test or a
general error-rate estimate. The case was selected after observing its failure,
so findings are exploratory and apply only to this fixed-source task.

- A source/request/integrity mismatch makes the affected evidence invalid for
  the intended contrast. Retain it and report the limitation; do not silently
  repair an input and replace its outcome.
- If all valid answers are correct, report that the historical failure was not
  reproduced. This neither clears routing-v2 nor proves equivalence. Stop.
- If errors recur without a clear condition-specific pattern, report unresolved
  answer reliability with correct source. No retrieval patch follows. Stop.
- A condition-specific pattern identifies a hypothesis for a separate decision,
  not a proven repair. Any proposed change must have a general mechanism and
  independently authored controls before a new workflow qualification is
  considered. Do not teach the product this fixture's expected answer.

The diagnostic completes when its frozen evidence has been independently
checked and its limits and outcome published, including an inconclusive outcome.
Its success criterion is an interpretable investigation, not obtaining correct
answers or qualifying the existing candidate.

## Work and acceptance boundary

The diagnostic is recorded as **W2.5.1.3.4.4 — Diagnose answer reliability with
fixed source** (`task_9a2ba0ae9e5776949cff119e74a7ce1a`), under W2.5.1.3.4 —
Qualify the repaired exploration workflow
(`task_ea390eab34f135070671da42c06f097d`). Preparation,
freeze, execution and interpretation belong to that bounded child. This
decision and its evidence review are complete; diagnostic execution is unstarted.

Keep every prior freeze, raw result, score and verdict immutable. The original
42-fixture-pass and per-task nonregression requirements remain unmet; this
diagnostic cannot complete parent delivery acceptance. W2.5.2 remains
prerequisite-blocked, multilingual W4 remains required and unstarted, and source
integration/shared-runtime promotion remain separate. There is no automatic
102-attempt rerun, acceptance relaxation, generic-shadow parser patch, or new
language implementation in this decision.
