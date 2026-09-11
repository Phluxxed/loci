# Existing-edge type context: completed matched comparison

**Decision: reject automatic expansion on every get under the frozen acceptance
rules.** The opt-in implementation works, but this batch does not establish the
required practical efficiency gain. Keep it isolated on
`feat/evidence-backed-exploration` as the tested basis for further work; it has
not been merged into the shared runtime.

All 102 fresh attempts answered correctly. A fully passed 51/51; B fully passed
50/51. Every attempt has independently verified source, call counts, delivered
costs and provider usage. There were no correctness retries or replacements.

| Frozen maintained-task measure | A | B | Result |
|---|---:|---:|---|
| Eligible-task median-call sum | 16 | 15 | 6.25% reduction; 20% required |
| Eligible tasks saving at least one median call | — | 1 | 2 required |
| Sum of output-byte medians, all three tasks | 72,909 | 83,988 | 15.2% increase; no increase allowed |
| Sum of gross-input-token medians, all three tasks | 271,370 | 277,311 | 2.2% increase; no increase allowed |
| Maintained full passes | 9/9 | 8/9 | Minimum passes met; per-task nonregression failed |
| All-nine nearest-rank p95 latency | 57.426 s | 60.576 s | 1.055×; within the 1.25× limit |

The eligible call comparison includes temporal arguments and renderer results,
which each fully passed all three repetitions in both arms. Retrieval limits
is ineligible because one B repetition failed a hard budget. Its costs, latency
and correctness outcome remain in the other gates. No metric or threshold was
changed after measurement. [All gates and attempts](report.md) and the
[machine-readable report](report-summary.json) retain the complete results.

## What was built

`loci_get(..., include_type_context=True)` adds bounded definitions and supporting
source from existing resolved type-only imports. It selects references by exact
declaration-byte ownership, follows at most three hops, deduplicates within the
response and reports omissions. It preserves the original graph edge identities,
default exact retrieval, search-selection lineage and graph diagnostics.

The [frozen selection contract](../../../docs/design/2026-09-11-existing-type-context.md)
defines the fixed anchor, node, reference, source and output limits. No new
parser, resolver, storage or graph semantics were added.

The B adapter automatically enables the opt-in on its existing get operation.
Both arms use the same adapter module, model-visible tool schemas and prompt.
A follows the unchanged exact-get path. Added definitions, support, metadata
and errors all retain their measured costs.

## What the evidence says

Imported-interface, imported-alias and named-re-export fixture medians improved
from 4 to 3, 8 to 5 and 5 to 3 calls respectively. The same-name distractor case
improved from 4 to 2. These gains did not satisfy the maintained-task gates.

Maintained call medians were 8 → 7 for temporal arguments, 12 → 12 for retrieval
limits and 8 → 8 for renderer results. Median exact-source recall was 1.0 → 1.0,
1.0 → 1.0 and 0.8 → 1.0 respectively. A correct answer or full pass does not
imply that every required source span was delivered.

B delivered 24 added definition occurrences and 35 selected reference
occurrences. Local aliases, local parameter/property types and explicit heritage
remain missing where current graph records cannot prove them. The renderer
tasks also receive the real imported dependency `TemporalQuery`, which is not
required context for those questions. Repeated gets can repeat related source.
These are reasons to improve coverage and selection, not to relax the gates.

Actual expanded gets reported no budget or ownership omissions in this batch.
Some context was already included in the requested roots; one re-export
repetition used file reads without issuing a get. The [per-case attribution](residuals.md)
separates those cases from missing relationships and the intentional unresolved
negatives. Gold-seeded [diagnostic probes](loci-existing-context-probes.json) are
retained separately and excluded from all agent metrics.

The one failed run, `anvil_retrieval_limits-r3-B`, began with an unscoped outline
of the maintained repository. Its oversized result was withheld before source
delivery. This happened before type expansion was used: it is not evidence that
the new get expansion overflowed. The frozen rules still retain its budget
failure despite the later correct answer. Two bounded input errors in repetition
one B also retain their costs.

The unchanged semantic scorer finds 15 available and one delivered gold
dependency link per arm, across 102 repeated requirements. A file-owned edge is
not relabelled as a function-to-type edge merely because declaration ownership
selected it for hydration. Both arms have zero authored forbidden proven links;
that negative gate is not an exhaustive semantic-soundness proof.

## Totals and reproducibility

| All 51 runs per arm | A | B |
|---|---:|---:|
| Observed calls | 285 | 252 |
| Complete response bytes | 381,153 | 433,384 |
| Delivered source bytes | 89,879 | 87,556 |
| Duplicate source bytes | 27,205 | 29,890 |
| Gross input tokens | 2,197,468 | 2,047,856 |
| Cached input tokens, included above | 1,579,520 | 1,472,000 |
| Output tokens, including reasoning | 30,094 | 28,824 |

All-nine maintained totals are 76 calls in each arm, 205,130 → 235,198 response
bytes and 734,521 → 775,019 gross input tokens. Global totals are reported for
completeness; the frozen acceptance rules use the maintained-task measures above.

Candidate and harness commit `564c152099b13f469cb336f1046829f8e8d9d07b`, followed
by freeze carrier `2379278b4bc2e85623cf64e180d5a2980511517c`, were published before
the first measured attempt. The candidate source tree is
`a7b0f5e94df1c25a8554a8119d3254d2c60771cc`. The
[freeze](../../comparisons/typescript-context-existing-v1/freeze.json) pins 16
harness, 104 unchanged corpus and 13 comparison-evidence files. Two descriptive
freeze-metadata errors are corrected in [provenance-errata.json](provenance-errata.json);
the frozen bytes remain intact.

The fixed schedule was 17 cases × three repetitions × two arms, serial A/B,
B/A, A/B. Each attempt used fresh source, index and Codex session. Luna high,
Codex 0.154.0, the v3 source/gold, common prompt, 13 typed operations, three
resource helpers and all numerical controls stayed fixed. Historical A-only
results are not the paired comparator. The unversioned model slug does not
prove fixed backend weights, and three source-comprehension tasks from one
repository do not establish broad coding or code-edit gains.

Before measurement, 20 focused type-context checks, one real MCP check, three
adapter checks, five report checks, nine runner checks and 194 existing
service/MCP/generic-shadow checks passed. The fresh batch repeated ten A offline
transport modes and one B expanded-get proof. Every actual effective request
matched the frozen canonical tool schema.

[Independent verification](verification.json) passed all 102 source/measurement
replays and host-call reconciliations, all 102 distinct trace/provider identities,
537 unique delivered attempts and complete usage/accounting, with zero integrity
failures. The valid budget failure remains a measured outcome. To replay:

```sh
.venv/bin/python benchmarks/results/typescript-context-existing-v1/artifact-verify.py \
  --output benchmarks/results/typescript-context-existing-v1 \
  --corpus-root benchmarks/corpora/typescript-context-v3 \
  --report /tmp/loci-existing-comparison-verification.json
```

The raw runner [summary](summary.json), generated report, verification and
diagnostic records are separate artifacts. [The inventory](artifact-sha256.json)
fingerprints the complete retained result packet.
