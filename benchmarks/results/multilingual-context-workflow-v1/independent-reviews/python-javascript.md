# W4.7 Python and JavaScript interim audit

## Scope

This is a read-only audit of the 48 completed synthetic Python and JavaScript rows in `/Users/brummerv/phluxxed/loci-exploration/benchmarks/results/multilingual-context-workflow-v1`. It covers four Python and four JavaScript cases, two arms, and three repetitions per case. The maintained Python case `python_loci_bundle_contract` is not included because it had not run at this boundary.

Throughout this note, an attempt name such as `python_alias_annotation-r1-A` denotes `<results root>/<attempt>/result.json`; its exact host transcript and adapter ledger are the adjacent `events.json` and `adapter-trace.json`. Frozen prompts, contexts, relationships, forbidden relationships, and gold answers are in `/Users/brummerv/phluxxed/loci-exploration/benchmarks/corpora/multilingual-context-v1/corpus.json`.

The corpus and protocol remain those frozen by preparation commit `c910c5ac252a7c982f784d87d61bc4c50fc0c0ec` and freeze commit `14cdf4c3061a74060e51cd7c682b56a40b9f1f9e`. This audit does not change, retry, rescore, replace, or complete any frozen measurement. It makes no final efficiency claim; final reporting and replay wait for all 114 retained attempts.

The established evaluator defects and their evidence are documented in `/Users/brummerv/phluxxed/loci-exploration/docs/reviews/2026-09-13-multilingual-measurement-defects.md`. Current result evidence takes precedence over preflight expectations.

## Frozen per-case counts

Each row below accounts for exactly three frozen attempts. `Ans` is `answer_correct`; `Meas` is `measurement_complete`; `Task` is `task_correct`; `Full` is `full_pass`; `Src=1` counts attempts with `context_recall == 1`; `Rel full` counts attempts whose frozen delivered relation total equals its required total. These are counts of retained fields, not reconstructed metrics.

| Case | Arm | Rows | Ans | Meas | Task | Full | Src=1 | Rel full |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `python_alias_annotation` | A | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| `python_alias_annotation` | B | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| `python_base_and_literal_forward` | A | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| `python_base_and_literal_forward` | B | 3 | 0 | 2 | 0 | 0 | 3 | 3 |
| `python_known_call_impact` | A | 3 | 1 | 0 | 0 | 0 | 3 | 0 |
| `python_known_call_impact` | B | 3 | 0 | 3 | 0 | 0 | 3 | 3 |
| `python_unproven_contracts` | A | 3 | 0 | 0 | 0 | 0 | 3 | 3 |
| `python_unproven_contracts` | B | 3 | 0 | 0 | 0 | 0 | 3 | 3 |
| **Python total** | A+B | **24** | **1** | **5** | **0** | **0** | **24** | **12** |
| `javascript_value_dependencies` | A | 3 | 2 | 0 | 0 | 0 | 3 | 0 |
| `javascript_value_dependencies` | B | 3 | 1 | 2 | 1 | 0 | 3 | 0 |
| `javascript_direct_class_base` | A | 3 | 3 | 0 | 0 | 0 | 3 | 0 |
| `javascript_direct_class_base` | B | 3 | 2 | 2 | 1 | 1 | 3 | 2 |
| `javascript_known_call_impact` | A | 3 | 2 | 0 | 0 | 0 | 0 | 0 |
| `javascript_known_call_impact` | B | 3 | 2 | 3 | 2 | 2 | 3 | 3 |
| `javascript_unproven_dependencies` | A | 3 | 0 | 0 | 0 | 0 | 3 | 3 |
| `javascript_unproven_dependencies` | B | 3 | 0 | 0 | 0 | 0 | 2 | 3 |
| **JavaScript total** | A+B | **24** | **12** | **7** | **4** | **3** | **20** | **11** |
| **Audited total** | A+B | **48** | **13** | **12** | **4** | **3** | **44** | **23** |

All 24 Arm A rows are measurement-incomplete because each contains at least one `graph_*` delivery rejected by the known public-ledger/internal-trace name mismatch. Twelve Arm B rows are complete and twelve are incomplete. There is therefore no complete A/B pair in this 48-row slice, so it cannot support a matched efficiency comparison.

`Rel full` needs context for the two zero-relation uncertainty cases: equality at `0/0` says the case requires no positive relation; it does not add a positive relationship success. It also does not override answer, source, measurement, or budget failures.

## Failure-category inventory

These are all categories present in `baseline.failures` across the 48 rows:

| Category | Instances | Affected rows | Classification |
|---|---:|---:|---|
| `delivery_trace_mismatch` | 146 | 36 | Known evaluator graph-name defect; one instance per affected `graph_*` delivery |
| `unmatched_recorded_delivery` | 36 | 36 | Derivative aggregate failure after graph trace IDs were not marked matched |
| `tool_error` | 40 | 22 | 37 pagination-bound errors plus 3 explicit-seed-count errors |
| `budget_exhausted` | 5 | 4 | Three provider input-token limits, one adapter evidence-span limit, and one task timeout |
| `provider_usage_ambiguous` | 1 | 1 | Timed-out row retained no `turn.completed` usage event |

No other failure category appears.

### Known graph reconciliation defect

The mechanism and affected surface remain exactly those established in `docs/reviews/2026-09-13-multilingual-measurement-defects.md`: the ledger retains the public `graph_*` name, the ReadTrace event retains `graph`, and `/Users/brummerv/phluxxed/loci-exploration/benchmarks/multilingual_context_observed.py:109-155` incorrectly uses one expected name for both. The mismatch affects graph anchors, neighbors, traversal, paths, retrieve, imports, references, and calls in either arm. It does not affect search, get, file, grep, outline, or `loci_explore`.

The 146 mismatches occur in 36 rows. Each of those rows also has the derivative unmatched-event failure. Under the frozen evaluator, their complete output bytes, aggregate source bytes, estimated source tokens, delivery verification, measurement completeness, and full pass remain withheld or false as recorded. Their frozen graph-delivery relation totals cannot be replaced from raw packets.

### Hidden pagination bound

Thirty-seven `tool_error` instances say `invalid record pagination`, across 22 rows. They are calls to `graph_imports`, `graph_references`, or `graph_calls` with a schema-valid `limit` of 50 or 100. The public schema declares only integer type, and the normalizer accepts it at `/Users/brummerv/phluxxed/loci-exploration/benchmarks/typescript_context_tools_v3.py:197-207`; the adapter applies a hidden maximum of 32 at `/Users/brummerv/phluxxed/loci-exploration/benchmarks/typescript_context_adapter.py:224-229`.

This is the established schema/adapter boundary defect. It is not evidence that a graph-record service returned incorrect source or resolution. The error responses, calls, and output remain retained.

### Hidden explicit-seed bound

Three additional `tool_error` instances say `explicit IDs exceed the frozen node/anchor limit`:

- `python_unproven_contracts-r1-B`, `graph_neighbors`, six seed IDs.
- `javascript_unproven_dependencies-r1-A`, `graph_retrieve`, seven seed IDs.
- `javascript_unproven_dependencies-r3-A`, `graph_neighbors`, seven seed IDs.

The published graph schemas accept an array of strings without `maxItems`; the shared normalizer accepts the arrays at `typescript_context_tools_v3.py:137-195`. The adapter applies `max_anchors`—five—to graph `seed_ids` at `typescript_context_adapter.py:191-195`. This is another schema/adapter contract-boundary limitation, closely analogous to the pagination bound. The calls do not establish an engine source or resolution defect.

### Why the frozen proof did not catch graph reconciliation

The passing `/Users/brummerv/phluxxed/loci-exploration/benchmarks/comparisons/multilingual-context-workflow-v1/scorer-verification.json` identifies its implementation as fresh fixture indexes plus direct `service.explore` packets. The passing sibling `transport-verification.json` covers exactly three modes: Arm A `get`, Arm B `loci_explore`, and an Arm B explore schema error. None sends a `graph_*` result through the multilingual reconciler. Likewise, `/Users/brummerv/phluxxed/loci-exploration/tests/test_multilingual_context_observed.py:46-108` exercises explicit explore replay, budget, and usage behavior, while `/Users/brummerv/phluxxed/loci-exploration/tests/test_multilingual_context_tools.py:31-114` checks arm schema equality and explore normalization/dispatch. The proof therefore established the source/proof scorer and the transports it actually crossed; it did not establish graph ledger-name reconciliation or graph pagination agreement. This explains the escaped boundary without weakening the checks that did run or suggesting an engine defect.

### Actual hard-budget and usage failures

The five retained hard-budget failures are independent of the graph-name mismatch:

- `python_unproven_contracts-r1-B`: 225,347 input tokens exceeds 200,000.
- `python_unproven_contracts-r2-B`: 253,364 input tokens exceeds 200,000; attempt 17 also exceeded `max_evidence_spans`, and its result was withheld by the adapter.
- `javascript_unproven_dependencies-r2-A`: 180.015 seconds exceeds the 180-second task limit. No `turn.completed` event exists, so `provider_usage_ambiguous` is also retained and provider usage is unavailable.
- `javascript_unproven_dependencies-r3-B`: 206,197 input tokens exceeds 200,000.

These failures remain failures. No later correct-looking answer, raw token inference, or partial output can replace the failed gate.

## Source, proof, forbidden-origin, and relationship evidence

Across all 48 frozen relationship objects:

- `forbidden_proven_relationships` is zero.
- `delivery_integrity_violations` is empty.
- No failure category reports an invalid source interval, content hash mismatch, delivered edge absent from the index, incomplete relationship proof, or forbidden delivered origin.

Those observations do not have equal strength in every row. Twelve measurement-complete rows certify their delivery accounting. In the other 36, the graph-name defect prevents complete delivery certification, so zero integrity and forbidden counts cannot be enlarged into an exhaustive absence claim. The raw artifacts nevertheless provide no positive evidence that Loci invented, altered, or misattributed source in this slice.

All 24 Python rows record `context_recall: 1.0`. JavaScript records full recall in 20 rows. The four source-incomplete JavaScript rows are:

- `javascript_known_call_impact-r1-A`: 4/7 required contexts (`add`, `make`, `method`, `run`).
- `javascript_known_call_impact-r2-A`: 4/7, the same four contexts.
- `javascript_known_call_impact-r3-A`: 6/7 (`add`, `arrow_export`, `import`, `make`, `method`, `run`).
- `javascript_unproven_dependencies-r2-B`: 4/6 (`barrel`, `entry`, `imports`, `remaining`).

These are genuine frozen source omissions by the observed workflows. The graph reconciliation defect does not create the trace recall values; source recall is computed from recorded source spans. Correct answers in `javascript_known_call_impact-r2-A` and `-r3-A` therefore do not turn those rows into source-complete passes.

The positive relationship evidence in complete Arm B rows is mixed:

- `python_base_and_literal_forward` delivers 2/2 in all repetitions.
- `python_known_call_impact` delivers 1/1 in all repetitions.
- `javascript_direct_class_base` delivers 1/1 in repetitions 1 and 2; repetition 3 invokes only JavaScript `type_dependencies`, returns the explicit `unsupported_language` omission, then uses graph calls affected by reconciliation, leaving 0/1.
- `javascript_known_call_impact` delivers 3/3 in all repetitions.
- `javascript_value_dependencies` delivers 2/3 in all repetitions. The missing relation is consistently `helper.js::make#function -> helper.js::add#function`. Actual `loci_explore` packets return both direct `run` call edges and explicitly report `alternative_path` omissions. The persisted relation is marked available, but the compact selection reaches `add` directly from `run` and omits the alternate `make -> add` path. This is a disclosed compact-selection coverage limitation for this corpus, not false source or a missing engine edge.

The Python alias case varies from 0/3 to 2/3 delivered in Arm B. Where `type_dependencies` is called, packets explicitly report `alternative_path` and omit one or more available alias/type paths; repetition 3 performs only `locate` and returns no relationship. This is workflow and compact-selection coverage evidence. It is not proof of an incorrect origin.

No Arm A positive relationship total can be used to compare retrieval effectiveness in this slice: all A rows are measurement-incomplete and graph relationship deliveries were rejected at the evaluator boundary.

## Answer failures

The frozen scorer compares against exact evaluator-only gold, including key names, value shapes, path spellings, and specified array order (`benchmarks/corpora/multilingual-context-v1/corpus.json:315-420`, `:429-530`, `:539-594`, `:603-726`, `:735-845`, and `:854-1045`). Thirteen of 48 answers are exactly correct; only four rows are `task_correct`, because accounting, source, or other requirements also apply. Three rows are full passes: `javascript_direct_class_base-r1-B`, `javascript_known_call_impact-r2-B`, and `javascript_known_call_impact-r3-B`.

### Prompt-visible contract versus evaluator-only gold

The task agent did not see the gold object or a complete answer schema. The corpus expressly marks answers and labels evaluator-only at `benchmarks/corpora/multilingual-context-v1/corpus.json:11`; controls set `gold_visible: false` and provide only the general JSON instruction at `benchmarks/comparisons/multilingual-context-workflow-v1/inputs/comparison-controls.json:57-61`. The runner constructs the request from `common_prompt`, the Arm B workflow guide when applicable, and the case prompt at `benchmarks/multilingual_context_compare.py:72-80` and `:226-232`.

The case prompts name fields and sometimes prescribe a shape—for example, `payload_fields` is a name-to-annotation object and `edge_direction` is an ordered pair—but they do not uniformly specify whether every origin is a filepath string rather than a file-plus-symbol value, whether uncertainty fields are flat booleans/lists rather than a per-name object, or whether an equivalent relative path must omit `./`. Therefore all retained `answer_correct: false` values remain valid outcomes under the frozen exact contract, but mismatches in those unshown conventions are answer-contract failures rather than demonstrated semantic source-comprehension errors. In particular, `payload_origin` forms that still identify `schema.py`, the nested per-name Python/JavaScript uncertainty objects when they preserve “unproven,” qualified caller/callee IDs that preserve direction, and `./contracts.js` must not be reported as wrong source facts solely because they differ from gold representation. Explicitly requested key names, requested array order, and the few actual fact/certainty errors below remain distinguishable.

Representative failure classes follow. These are classifications of retained answers against frozen gold, not retrospective scores.

### Structural or exact-encoding failures

- All six `python_alias_annotation` answers encode the correct `schema.py` origin at a different granularity or in a different value form: a `[file, symbol]` list, `schema.py::Payload`, `schema.py::Payload#class`, or `schema.Payload`, instead of the evaluator-only gold string `schema.py`. See `python_alias_annotation-r1-A/result.json:480-492` and the other five case result files. This is an exact-contract mismatch, not a demonstrated false-file-origin claim.
- Five of six `python_known_call_impact` answers use qualified symbol IDs in `edge_direction` instead of the required `["caller", "target"]`. `python_known_call_impact-r2-A` is the sole exactly correct answer, but it remains measurement-incomplete.
- `python_base_and_literal_forward-r2-B` nests the requested fields under `Child` and `later`; the other repetitions use `schema.Base` rather than `schema.py` and generally `schema.Payload` rather than `schema.py::Payload`.
- Every `javascript_unproven_dependencies` answer has the wrong JSON structure: some use empty arrays where booleans are required; others place all requested fields inside a `proven_targets` object; the timed-out `r2-A` answer is `{}`. The empty values generally preserve the negative meaning but do not satisfy the specified object.
- `javascript_known_call_impact-r1-A` renames `direct_callers` to `known_direct_callers`; `r1-B` returns the right callers in the wrong required sort order.
- `javascript_value_dependencies-r2-A`, `r2-B`, and `r3-B` use a per-callee object for `helper_origin` rather than the required string.
- `javascript_direct_class_base-r2-B` reports `./contracts.js`; gold requires `contracts.js`. This names the same file with an equivalent relative spelling and is only an exact-contract mismatch, rather than a different origin.

### Genuine wrong facts or certainty errors

- `python_base_and_literal_forward-r1-A` returns bare authored spelling `P` for `literal_forward_target`; gold requires the resolved exact target `schema.py::Payload`. The other values still identify the correct base concept but use non-gold origin notation.
- `javascript_value_dependencies-r3-B` reports `add_expression: "add(1)"`; gold is the helper implementation expression `"value + 1"`.
- `python_unproven_contracts-r1-B`, `r2-B`, and `r3-A` place the ambiguous `Choice` candidates and `negative.py::shadowed.P#constant` under `exact_repository_targets`, although gold requires an empty list. This is false exact-target certainty as well as a structural mismatch. `r3-B` labels the alternatives ambiguous inside a nested object, preserving uncertainty but still violating the required top-level shape. `r1-A` and `r2-A` keep all nested target lists empty and fail structurally rather than by asserting a false origin.

There is no demonstrated wrong-origin source delivery. Reading a decoy file is not itself a claim; the scorer records zero forbidden proven relationships in every row.

## Row-level accounting appendix

This appendix makes the 48-row coverage explicit. Columns are frozen `answer_correct`, `measurement_complete`, `task_correct`, `full_pass`, source recall, delivered/required relations, and failure counts. `G` means graph delivery mismatch, `U` unmatched-recorded aggregate, `P` pagination tool error, `I` explicit-seed tool error, `B` budget failure, and `V` provider-usage ambiguity.

| Attempt | Ans | Meas | Task | Full | Source | Relations | Failures |
|---|---:|---:|---:|---:|---:|---:|---|
| `python_alias_annotation-r1-A` | 0 | 0 | 0 | 0 | 1 | 0/3 | G3 U1 P1 |
| `python_alias_annotation-r1-B` | 0 | 0 | 0 | 0 | 1 | 2/3 | G4 U1 P3 |
| `python_alias_annotation-r2-A` | 0 | 0 | 0 | 0 | 1 | 0/3 | G6 U1 P1 |
| `python_alias_annotation-r2-B` | 0 | 0 | 0 | 0 | 1 | 1/3 | G1 U1 P1 |
| `python_alias_annotation-r3-A` | 0 | 0 | 0 | 0 | 1 | 0/3 | G4 U1 |
| `python_alias_annotation-r3-B` | 0 | 0 | 0 | 0 | 1 | 0/3 | G1 U1 |
| `python_base_and_literal_forward-r1-A` | 0 | 0 | 0 | 0 | 1 | 0/2 | G2 U1 |
| `python_base_and_literal_forward-r1-B` | 0 | 1 | 0 | 0 | 1 | 2/2 | none |
| `python_base_and_literal_forward-r2-A` | 0 | 0 | 0 | 0 | 1 | 0/2 | G4 U1 |
| `python_base_and_literal_forward-r2-B` | 0 | 1 | 0 | 0 | 1 | 2/2 | none |
| `python_base_and_literal_forward-r3-A` | 0 | 0 | 0 | 0 | 1 | 0/2 | G5 U1 P3 |
| `python_base_and_literal_forward-r3-B` | 0 | 0 | 0 | 0 | 1 | 2/2 | G1 U1 |
| `python_known_call_impact-r1-A` | 0 | 0 | 0 | 0 | 1 | 0/1 | G1 U1 |
| `python_known_call_impact-r1-B` | 0 | 1 | 0 | 0 | 1 | 1/1 | none |
| `python_known_call_impact-r2-A` | 1 | 0 | 0 | 0 | 1 | 0/1 | G2 U1 P1 |
| `python_known_call_impact-r2-B` | 0 | 1 | 0 | 0 | 1 | 1/1 | none |
| `python_known_call_impact-r3-A` | 0 | 0 | 0 | 0 | 1 | 0/1 | G2 U1 |
| `python_known_call_impact-r3-B` | 0 | 1 | 0 | 0 | 1 | 1/1 | none |
| `python_unproven_contracts-r1-A` | 0 | 0 | 0 | 0 | 1 | 0/0 | G5 U1 P1 |
| `python_unproven_contracts-r1-B` | 0 | 0 | 0 | 0 | 1 | 0/0 | G7 U1 P2 I1 B1 |
| `python_unproven_contracts-r2-A` | 0 | 0 | 0 | 0 | 1 | 0/0 | G5 U1 P2 |
| `python_unproven_contracts-r2-B` | 0 | 0 | 0 | 0 | 1 | 0/0 | G7 U1 P2 B2 |
| `python_unproven_contracts-r3-A` | 0 | 0 | 0 | 0 | 1 | 0/0 | G6 U1 P2 |
| `python_unproven_contracts-r3-B` | 0 | 0 | 0 | 0 | 1 | 0/0 | G5 U1 P1 |
| `javascript_value_dependencies-r1-A` | 1 | 0 | 0 | 0 | 1 | 0/3 | G3 U1 |
| `javascript_value_dependencies-r1-B` | 1 | 1 | 1 | 0 | 1 | 2/3 | none |
| `javascript_value_dependencies-r2-A` | 0 | 0 | 0 | 0 | 1 | 0/3 | G3 U1 |
| `javascript_value_dependencies-r2-B` | 0 | 0 | 0 | 0 | 1 | 2/3 | G2 U1 |
| `javascript_value_dependencies-r3-A` | 1 | 0 | 0 | 0 | 1 | 0/3 | G3 U1 |
| `javascript_value_dependencies-r3-B` | 0 | 1 | 0 | 0 | 1 | 2/3 | none |
| `javascript_direct_class_base-r1-A` | 1 | 0 | 0 | 0 | 1 | 0/1 | G1 U1 |
| `javascript_direct_class_base-r1-B` | 1 | 1 | 1 | 1 | 1 | 1/1 | none |
| `javascript_direct_class_base-r2-A` | 1 | 0 | 0 | 0 | 1 | 0/1 | G5 U1 |
| `javascript_direct_class_base-r2-B` | 0 | 1 | 0 | 0 | 1 | 1/1 | none |
| `javascript_direct_class_base-r3-A` | 1 | 0 | 0 | 0 | 1 | 0/1 | G3 U1 |
| `javascript_direct_class_base-r3-B` | 1 | 0 | 0 | 0 | 1 | 0/1 | G4 U1 P1 |
| `javascript_known_call_impact-r1-A` | 0 | 0 | 0 | 0 | 0.571 | 0/3 | G4 U1 P1 |
| `javascript_known_call_impact-r1-B` | 0 | 1 | 0 | 0 | 1 | 3/3 | none |
| `javascript_known_call_impact-r2-A` | 1 | 0 | 0 | 0 | 0.571 | 0/3 | G4 U1 P1 |
| `javascript_known_call_impact-r2-B` | 1 | 1 | 1 | 1 | 1 | 3/3 | none |
| `javascript_known_call_impact-r3-A` | 1 | 0 | 0 | 0 | 0.857 | 0/3 | G5 U1 P2 |
| `javascript_known_call_impact-r3-B` | 1 | 1 | 1 | 1 | 1 | 3/3 | none |
| `javascript_unproven_dependencies-r1-A` | 0 | 0 | 0 | 0 | 1 | 0/0 | G8 U1 P1 I1 |
| `javascript_unproven_dependencies-r1-B` | 0 | 0 | 0 | 0 | 1 | 0/0 | G6 U1 P2 |
| `javascript_unproven_dependencies-r2-A` | 0 | 0 | 0 | 0 | 1 | 0/0 | G8 U1 P3 B1 V1 |
| `javascript_unproven_dependencies-r2-B` | 0 | 0 | 0 | 0 | 0.667 | 0/0 | G3 U1 P3 |
| `javascript_unproven_dependencies-r3-A` | 0 | 0 | 0 | 0 | 1 | 0/0 | G7 U1 P1 I1 |
| `javascript_unproven_dependencies-r3-B` | 0 | 0 | 0 | 0 | 1 | 0/0 | G6 U1 P2 B1 |

The appendix sums to 48 rows, 146 `G`, 36 `U`, 37 `P`, 3 `I`, 5 `B`, and 1 `V`, matching the category inventory.

## Report-safe conclusion for this 48-row slice

The directly supported conclusion is limited: three Arm B JavaScript attempts are full passes, no Python attempt is a full pass, and 36 rows are measurement-incomplete because they invoked the frozen graph reconciliation defect. Four rows have actual source omission and four rows have hard-budget failures. Many exact answer failures reflect evaluator-only representation conventions and do not independently demonstrate factual source-comprehension errors. The retained genuine wrong facts are the Python unresolved `P` target and JavaScript `add_expression`; several Python uncertainty answers also assert exact targets despite the prompt's explicit ambiguity boundary. Complete rows contain no forbidden relationship or proof-integrity violation. Across all raw evidence inspected, there is no demonstrated Loci invented-source, false-origin delivery, or source-integrity defect. The repeated `alternative_path` omissions show bounded compact-selection coverage limits, especially the unreturned JavaScript `make -> add` edge, while the persisted edge remains available and the omission is explicit.

No null output/source metric is replaced, no incomplete row is promoted, and no arm-level efficiency recommendation is made.
