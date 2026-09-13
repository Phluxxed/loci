# Frozen three-arm type-context comparison

W2.5.1, declared on 11 September 2026 before measured requests. Canonical Task:
`task_b5c20c6eac6a941be4257458f0a7f80b` in Objective
`obj_0110c8712b21bdd2c12532f189d84a74` at `/Users/brummerv/loci`.

This comparison preserves the [v3 controls](../../corpora/typescript-context-v3/comparison-controls.md),
source snapshots, gold, thirteen typed retrieval operations, common prompt,
model route, observation protocol and numerical gates. It adds the missing
three-arm runner and source isolation without modifying the historical harness.

| Arm | Pinned source | Retrieval policy |
|---|---|---|
| A | `9acd3e3589ddc034cade36e03c26c4508e9d4434`, extractor 24 | Exact get and explicit graph retrieval. |
| B | `564c152099b13f469cb336f1046829f8e8d9d07b`, extractor 24 | The same operations, automatically enabling bounded type context on get over existing imported type references. |
| C | `0ad281fbe476ab9e2b9d0f1f9fa08a817618c77b`, extractor 25 | The same get-expansion policy and limits, with proven declaration-owned type dependencies and heritage. |

The [source audit](source-diff-audit.json) records the source trees, full diff
hashes, unchanged service definitions, identical limit declarations and shared
traversal helpers. C adds the record-ownership and relation-kind handling
necessary to consume its new semantics. The intended difference is not hidden
behind a shared current index: every attempt starts a fresh Python worker with
the selected source tree, creates a fresh snapshot and index using that engine,
and launches the MCP adapter with the same explicit source path. The source
files and extractor identity are checked against the declared arm.

The frozen adapter does **not** expose `loci_explore`. W2.4's intent selection,
query-based pruning and compact result packer are outside this measurement.
This batch can establish the value of additional type relationships in the
automatic-get workflow; it cannot establish gains for the new intent workflow.

There are exactly **153 serial attempts**: 17 cases in corpus order, three
repetitions per case, with arm orders A/B/C, B/C/A, C/A/B. A and B are rerun;
their earlier results are historical evidence, not this batch's comparators.
GPT-5.6 Luna high runs through Codex 0.154.0 with the existing ChatGPT login.
No additional provider or specialist model is involved. Dollar costs remain
unavailable under the frozen ChatGPT accounting contract.

Before measurement, all 17 endpoints are checked independently in each engine.
The fresh batch catalog drives ten offline A transport probes plus one expanded
get probe each for B and C. Every probe captures the exact next model request
and reconciles the complete delivered payload, source and observed call count.
All three retain the same canonical tool-schema hash. These deterministic
transport probes make no provider model requests. Each subsequent measured
attempt separately audits its actual model-visible request and source boundary.

The new worker reuses the frozen attempt lifecycle, bounded errors, source and
cost validators, timeout handling and relationship scorer. Its only runtime
bindings are the declared adapter module, selected source engine and corresponding
source provenance. The C adapter preserves C in its trace while applying the
same validated get dispatch as B. Every added definition, support line, metadata
field and error remains charged to its outer get operation.

Code, report implementation and this declaration are committed before the
freeze file is created. The freeze pins that code commit, every used harness
file, unchanged corpus files, premeasurement evidence and each arm's complete
source file map. The freeze is then committed and published before any measured
request. Batch provenance retains its carrier commit, fresh model catalog,
environment, raw host events, exact outputs and hashes.

The report evaluates B/A, C/B and C/A under the unchanged gates. Read reduction
means **all observed top-level retrieval calls**, including errors, empty results,
helpers, duplicate reads and necessary verification. V1/v2 causal “avoidable
reads” are not collected or inferred. Candidate full passes require correct
answers, verified complete measurements and compliance with all hard limits.
Missing measurements remain inconclusive. Failures never become efficient wins.

There are no correctness retries. A confirmed provider or host outage permits
at most one replacement of the entire matched case/repetition block, retaining
the original. This runner stops at an unfinished worker and refuses to overwrite
it; any permitted replacement needs its own explicit retained block record.
Completed attempts may be resumed only under identical frozen identities.

C's improvement over A does not by itself establish incremental benefit from
new semantics. That claim also requires the frozen C/B benefit gates. A rejected
or inconclusive candidate remains in the complete report. These three maintained
source-comprehension tasks come from one repository and cannot establish broad
coding or code-edit gains. No merge or runtime promotion follows automatically.

Run with a freshly prepared model catalog:

```sh
.venv/bin/python -m benchmarks.typescript_context_three_arm \
  --catalog /tmp/loci-abc-catalog/model-catalog.json \
  --engine-root /tmp/loci-abc-engines \
  --output benchmarks/results/typescript-context-three-arm-v1
```

Generate the report separately so the runner's raw summary is preserved:

```sh
.venv/bin/python -m benchmarks.typescript_context_three_arm_report \
  --output benchmarks/results/typescript-context-three-arm-v1 \
  --corpus-root benchmarks/corpora/typescript-context-v3 \
  --comparison-root benchmarks/comparisons/typescript-context-three-arm-v1
```
