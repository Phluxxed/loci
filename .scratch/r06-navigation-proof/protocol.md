# R0.6 prospective protocol

Terminal decision: whether path-aware source acquisition and optional targeted
semantic proof should remain separate, with measured coverage and added cost.
This is an experiment and assessment, not an adopted architecture or V2 plan.
Reuse the R0.5 worktree and architecture harness; protect both main checkouts,
R0.3/R0.4 references, all historical scorers and results. No production edits or
model campaign. Two fresh repetitions alternate arm order; immediate repeat in
each worker measures identical requests, without claiming cold OS caches.

## Fixed source navigation

Compare R0.4/R0.5 GraphFreeSource lexical scheduling against the new pure path
scheduler. Keep five acquisition and sixteen continuation calls, 128 KiB source
and 256 KiB packet soft admission limits, inventory separately charged. The
path scheduler sees only delivered source and filename/hash/size inventory.
Expand incomplete delivered files, follow observable relative JS import/reexport
and Rust module paths and delivered Cargo local paths, then lexical fallback.
All admitted alternatives remain source candidates. No graph/parser imports,
semantic bindings, evaluator context, missing spans or per-case routing rules.
Time selection, archive exact query provenance/work, independently replay it.

## Fixed optional proof acquisition

Control is pinned R0.5 5fc52cb, with its five acquisition/one semantic-question
policy. Candidate retains the exact native objects and source/control bytes
already computed for that question; it revalidates the full current inventory
before/after each proof request. It neither expands the slice nor reruns native
resolution. Support-source extraction can still parse declarations, and all
such work is included in CPU/elapsed/RSS. Raw retained bytes and native index
serialization proxy are additional memory, not zero-cost caching.

After the unchanged five-slot base acquisition, request up to four exact
previously delivered semantic node identities, in first encounter order:
anchors before other nodes, excluding file/crate/package identities and prior
focused requests. Each call uses only edges incident to that identity, proof
first, with unchanged complete caller/target/import/reexport/module/control
support. Newly returned identities may become later requests. Never use audit
projection IDs, expected edges, scorer output or gold to select a request.
The first original anchor may be requested because proof-first differs from
the initial source-first response. Four calls are a measured heuristic, not an
exhaustive search of every possible consumer request.

Two predeclared variants: focused uses 8 KiB unique evidence/16 KiB envelope per
call; focused-wide uses 32 KiB/64 KiB per focused call, retaining 8/16 for its
initial semantic response. The wider variant diagnoses bounded packet capacity;
per-attempt evidence and envelope sizes distinguish their pressure. It is not
equal-budget evidence of selection improvement. Both share the original soft
128/256 KiB case admission limits, with actual overshoot recorded and charged.
No proof pagination or session-only promotion of incomplete claims is added.

Native unresolved observations are summarized before packing, so uncertainty
uses the same envelope budget. Preserve raw native reason/family counts, up to
eight location examples, omitted-example count, external/ambiguous/inaccessible
and configuration-dependent omissions, and possible configuration semantics.
The summary is explicitly of the computed slice, non-exhaustive, and does not
turn unknowns into relationship claims. Python/Go remain unsupported separately.

## Targeted schedule and broader gate

Begin with anvil_temporal_arguments, anvil_retrieval_limits,
rust_contained_optional_reexport and rust_unproven_contracts. Run source versus
path, R0.5 versus focused, and focused versus focused-wide, serially. Independent
source-byte, schema, strict packet/session proof and structural checks must pass
and replay before expanding. A supported negative result is valid; do not tune
policy after observed scored misses.

Expand source/path to the frozen corpus if targeted path recovery is nonzero
without semantic imports, to check coverage changes beyond the motivating cases.
Expand focused comparisons if targeted proof acquisition is sound and either
recovers proof or diagnoses concrete bounded capacity failures; the retained
all-20 audit independently identifies alias/mixed-direction selection losses in
the corpus, which justifies testing those same frozen cases. No unrelated corpus
or live agent campaign is permitted.

## Accounting and interpretation

Retain source coverage, available native relationships, independently validated
packet proof, strict session proof, unsupported/incorrect claims and unknown task
answer correctness separately. Strict historical TypeScript/multilingual scorers
are unchanged; observer additions validate the fixed new operations and caps.
Archive first/repeat packet bytes, proof request identities, source/control
hashes, query provenance, native projection, work and failures. Invalid support
remains invalid even if the desired source later appears.

Measure setup/index/source selection/acquisition/proof/continuation wall and CPU,
worker child CPU and high-water RSS, output/source duplication, runtime file
store, retained raw/native memory proxy and evidence archive storage. Nested
phase timings are attribution, not additive cost. Independent observer/replay
cost is separate. Both repetitions' capabilities must agree; timings remain
descriptive. Agent task correctness remains unmeasured.

The retained R0.5 audit accounts for 20 native-supported losses: 11 selection,
9 packet-capacity, zero solely closure-gated in that set. General closure and
unresolved records remain distinct negative findings. Preserve exact edge-level
attribution and all historical packet failures. Stop after the architectural
assessment and publication of the experiment branch, with no integration.
