# Loci R0 architectural assessment

Status: active. Production source and existing dirty work preserved. Baseline f41b3eaa4c7871c68972de5f760572a6bcbe1760; R0.1 benchmark changes remain in primary and are evidence, not serving-code changes. Report owner: primary; output docs/reviews/2026-10-22-loci-r0-architecture.md. Experiments only in dedicated .worktrees/r0-* worktrees, isolated stores. No redesign/integration or sandbox investigation.

## Delegation plan

- architecture-index: reconstruct indexing/parser/storage and non-normal surfaces from live code and rationale. Read-only production; write .scratch/loci-r0/index-architecture.md. Acceptance: end-to-end paths, dependencies, duplication, source locators and candidate separable ablations. Sol/high/fork none.
- evidence-map: inspect existing evaluations and fixtures including corrected R0.1; distinguish mechanism delivery from task usefulness. Read-only production; write .scratch/loci-r0/evaluation-evidence.md. Acceptance: concrete reusable fixture entrypoints/gold, historical results with limits, priority experiment recommendations. Sol/high/fork none.
- primary: normal retrieval/read path, experimental controls, ablations, final synthesis.

- selection-ablation: isolate metadata-first anchor discovery versus literal-first on existing fixtures plus the reproduced literal-shadow case. Exclusive .worktrees/r0-selection and .scratch/loci-r0/selection-*; no shared stores. Sol/high/fork none. Acceptance: controlled run, intended evidence target, quality/resource deltas, source diff and limitations, no production integration.

## Isolation

/.worktrees/ already ignored; git check-ignore verified. Control and selection worktrees detached from f41b3ea. Serving src unchanged in primary. Control uses only tracked serving/tests/fixtures; R0.1 dirty benchmark changes are not needed by deterministic retrieval runs and are inspected as evidence.

## Returned work and reuse

architecture-index note: .scratch/loci-r0/index-architecture.md; adopted as source map, quantitative claims await experiments. evidence-map note: .scratch/loci-r0/evaluation-evidence.md; adopted as fixture/provenance guide with selected-corpus limitation.

Reusing evidence_map (Sol/high/fork none retained) for corpus ablations: its retained context owns precisely the corpus/scorer/control contracts. Scope now exclusive .worktrees/r0-control (enrichment toggle) and .worktrees/r0-ownership (representative-member bypass), outputs .scratch/loci-r0/corpus-*. Acceptance: frozen gold spans/relations and current normal packet adapter; paired direct retrieval with validated shared inputs, raw packets/timings/CPU/output/coverage per case; clear no task-completion inference; existing focused controls. 17 TypeScript v3 plus 19 multilingual cases, same explicit gold anchor used in both arms to isolate enrichment. No newly invented request budgets; existing fixed product limits. Primary owns validation-cache experiment.

Reusing architecture_index (Sol/high/fork none) for parse-reuse ablation; retained context maps all three parse consumers and trust dependencies. Exclusive .worktrees/r0-parse; outputs .scratch/loci-r0/parse-*. Acceptance: record control first; same source/semantic extraction passes; reuse only exact grammar+bytes tree within a bounded index operation; normalized semantic/index equality, parse invocation/wall/CPU/memory counts, focused invalid-syntax/language checks. No production refactor; experimental wrapper only; report overhead and no AST-walk saving.

Validation experiment predeclared: .worktrees/r0-validation/r0_validation.py. Control repeats IndexStore.validate_graph_state; candidate caches one validated state keyed by every symbol/hash/graph input and deep-copies on hits. Source freshness/full JSON loading/source containment/hash/UTF8/budgets unchanged. Inputs: frozen TS v3 imported_interface and maintained Anvil snapshot187 archived files, baseline f41b3ea (not historical serving baseline). Measure exact full-service fresh retrieve/read packets, cold/nochange indexing, three warm repetitions plus first calls, wall/CPU/counts/profile/output/storage. Negative controls: graph schema corruption, duplicate endpoint, cached mutable-state isolation and live source drift. One cache input, one mechanism; no claim of safe production cache design or task outcome.

## Final disposition

Assessment complete; no production redesign/integration. Main report docs/reviews/2026-10-22-loci-r0-architecture.md includes diagram, path/rationale map, classifications, controlled results, costs, alternatives and next experiments.

- selection_ablation: selection-ablation.md and selection-diff.patch adopted as supported negative for blanket literal-first, with diagnostic-only/single-timing limits.
- evidence_map reuse: corpus-ablation.md, final corpus-control-direct and corpus-ownership-direct artifacts adopted. Gold-informed anchors/selected corpora/no hydration limit task inference. Five strict-support call discrepancies remain uncredited and uncertain; source/evidence-line validation is narrower. Initial adapter and service-route runs retained, final direct runner sources exact; reconstructed intermediate runner identity unverified.
- architecture_index reuse: parse-ablation.md, parse-full.json and Swift/error/focused checks adopted. 913/1388 backend parses avoided, 63 exact index equalities/17 sampled packet equalities; ~1.3% instrumented wall gain and Anvil +53MB traced heap. Separate ownership walks retained; no integration recommended.
- primary validation: validation-ablation.md, raw results/profile and candidate67checks adopted. Complete full-service packets equal; guarded digest/deepcopy cache modest gains with cost displaced, no adoption conclusion.

Validation ends at directly relevant checks and artifact/preservation readback. No further agent run/review or confidence pass is required. No live model campaign; overall task efficiency and graph-free alternative remain unproven.
