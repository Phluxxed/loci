# Existing-edge type-context comparison

This is the premeasurement contract for W2.2. It uses the unchanged
[`typescript-context-v3` corpus and controls](../../corpora/typescript-context-v3/README.md).
The candidate adds the [bounded type-context opt-in](../../../docs/design/2026-09-11-existing-type-context.md).

The fresh batch has 102 attempts: 17 cases, three repetitions, both arms. Case
order is fixed; repetition orders are A/B, B/A, A/B. Each attempt gets a fresh
source snapshot, prebuilt index, Codex session and runtime. There are no
correctness retries. GPT-5.6 Luna high, Codex 0.154.0, source gold, common prompt,
thirteen typed operations, three resource helpers and all v3 limits remain fixed.

- **A:** the frozen v3 exact get and explicit graph operations.
- **B:** the same operations, with `include_type_context=True` automatically
  enabled by the evaluator's get adapter. Added source, support, metadata and
  errors all retain their measured costs.

The experiment exposes the same model-visible schemas and prompt in both arms.
The production MCP tool exposes the opt-in flag; the evaluation adapter fixes
that policy by arm to isolate its contribution. The source audit proves that
every prior service definition and all parser/resolver/storage files remain
unchanged. Original graph edges remain unchanged even when a selected reference
record belongs to a more specific declaration.

`freeze.json` identifies the candidate code/harness commit and source tree,
current and pinned file fingerprints, the unchanged corpus, and this comparison's
evidence. That code commit precedes the commit carrying the freeze file; both
are published before any measured request. The result manifest records the
actual publication commit and freeze-file hash. No measured code is changed
within the batch.

The candidate endpoint preflight covers all 17 cases. A deterministic offline
Codex/MCP proof captures the added type definition in the next model request and
reconciles its exact costs. Batch startup repeats the ten frozen A transport
modes and the added B get proof with the fresh model catalog, then audits the
effective request for every measured attempt. These probes make no model calls.

For relationship accounting, the new response container's actual canonical
edge objects are exposed to the unchanged v3 gold scorer. Their source, target,
resolution and evidence are not rewritten. The selected declaration ownership
is separately returned and verified; a file-owned edge is not relabelled as a
new function-to-type semantic edge. The authored forbidden-case gate retains
its limited scope.

Acceptance uses the unchanged v3 observed-call, correctness, source-recall,
output-byte, gross-input-token and p95-latency gates. The report is frozen and
tested before measurement. Complete measurements are required; unknown costs
never become zero. Historical A-only results are not the paired comparator.
Failures and a rejected or inconclusive candidate remain in the report.

Run after preparing a fresh catalog with the existing `prepare_catalog` helper:

```sh
.venv/bin/python -m benchmarks.typescript_context_compare \
  --catalog /tmp/loci-existing-fresh-catalog/model-catalog.json \
  --output benchmarks/results/typescript-context-existing-v1
```

Generate the report without replacing the runner's raw summary:

```sh
.venv/bin/python -m benchmarks.typescript_context_compare_report \
  --output benchmarks/results/typescript-context-existing-v1 \
  --corpus-root benchmarks/corpora/typescript-context-v3 \
  --comparison-root benchmarks/comparisons/typescript-context-existing-v1
```

The interpretation must distinguish missing existing relationships, declaration
ownership exclusions, budget omissions and context the agent never requested.
This slice does not add local type dependencies or new heritage semantics.
The three maintained tasks are source-comprehension tasks from one repository;
they do not establish broad coding or code-edit gains.
