# R0.5 prospective demand semantics proof protocol

Implementation audit scope added before the scored run: an independent,
read-only structural import/reexport proof check is needed because the frozen
semantic scorers exclude `imports` and `imports_type`. The check lives in
`benchmarks/architecture_structural.py`, with focused tests, and applies only
to the demand arm. It does not change the frozen semantic scorers or repair
historical R0/R0.4 packet failures.

This is a read-only audit and prospective evaluation contract for the isolated
R0.5 experiment. It does not change the frozen TypeScript v3 (17 cases),
multilingual v1 (19 cases), their authored spans/relationships/negatives, or
the strict semantic scorers. The experiment compares the retained R0.4
graph-free acquisition policy, a demand-driven candidate, and R0.3 eager
graph. First run the targeted Anvil reverse-caller and Rust optional
reexport/module cases; run all 36 only if the targeted result shows useful
recovery. A negative result on the targeted cases can finish the experiment.

## Freeze the question, then score it

The worker receives the case's initial `requests(corpus)` query. It may inspect
its *own* delivered packets,
source bytes, and the common filename/hash/size discovery inventory. It must
not receive `case.context`, `case.relationships`, forbidden relationships,
authored answer, `question_kind`, missing-span list, scorer output, or a
baseline index. Those remain evaluator-only. No scored miss can alter the
question schedule or policy for a later case or repetition.

Apply one deterministic semantic-context rule to every demand case:

1. Identify the entry from the initial authored query and returned source or
   node identity. If multiple candidates remain, retain ambiguity; do not
   select using gold context. Source-only/file queries remain source-only until
   an identity is established from observed source.
2. Ask for **forward** type, call, reference, import and reexport dependencies
   of that entry, then **reverse** callers/uses of the same entry. This is the
   task-level question for Anvil as well: its entry can lead to the imported
   input and its omission, stop, reporting and diagnostic contracts, while
   reverse traversal can surface callers. Neither direction is a case-specific
   exception.
3. Expand only newly observed resolved endpoints and binding routes under a
   fixed depth/call/byte budget, in stable encounter order. Two semantic hops
   from the entry cover nested input members; Rust import/reexport/module
   routes must follow observed `use`, `pub use`, external `mod`, crate/workspace
   and feature declarations as a control closure. Record every discovery,
   parse and resolution step, including negative lookups. If closure or budget
   is incomplete, report partial/unknown rather than an absent dependency.

Freeze the exact traversal depth, tie order and limits in the runner before a
scored execution, and apply them identically to all 36 demand cases. Keep
R0.4's authored entry query, five acquisition operation slots, sixteen
continuations, 128 KiB source and 256 KiB response soft admission limits.
The demand arm spends the **second of five** slots on one
`semantic_context(initial query)` after its first graph-free response. R0.3
spends its five slots on source retrieval with implicit eager semantics; R0.4
spends them on lexical source retrieval. This interface difference is a
reported comparison property, not an extra free demand call. All operations
and full responses, including overshoot, are charged. Never use a privileged
fixture-derived request for the demand arm. The shared inventory is an
explicit benchmark adapter, not a native capability attributed to a service.

## Independent proof observer

Use `benchmarks/architecture_cases.py` to verify frozen snapshots, every
packet's source bytes and whole-file hash, envelope bytes, source coverage,
and the R0.4 acquisition trace. Keep the frozen TypeScript scorer
(`typescript_context_explore_relationships.py`) and multilingual scorer
(`multilingual_context_relationships.py`) unchanged. Run them against a
candidate-produced sparse index projection and actually delivered packets.
The projection may be a minimal JSON `index` with `symbols` and `graph`
fields rather than a fully hydrated `GraphIndexState`, because the scorers
consume those JSON fields. It must be serialized by the candidate from its
own observed resolver records, not assembled from baseline/gold records by
the evaluator. A `GraphIndexState` wrapper is acceptable only if it is
sparse and includes the same authentic candidate records; filling it with a
full eager graph would invalidate the demand claim and its cost accounting.

The projection must be archived after each semantic question, before the
independent observer scores it. The receipt must bind it to the candidate
implementation, question, snapshot hashes and native resolver output; the
observer may only deserialize it. It must include **all** candidate-created resolved and
unresolved/ambiguous records for the requested slice, without gold filtering:
exact symbol IDs, files, spans and content hashes; native call,
`type_relations`, `symbol_references`, and import records; raw locations,
resolution statuses/configuration, support, resolution controls/control-file
hashes, Rust parent module observations, and the materialized edges actually
claimed. It must retain the `graph.input_hashes` needed to validate control
files. A matching source span or an edge synthesized from text alone earns no
semantic credit. The candidate may emit a native-shaped relationship only
when its **complete relation-linked support** fits the fixed 16 KiB output
and 8 KiB source cap for this semantic operation. It may deliver narrow
target-source items and continuations for discovery; if support does not fit,
omit the proof claim and report the limitation. It must not mark a pending or
partial proof complete. The observer joins each claimed edge to a candidate record
and checks the complete persisted support and control intervals in delivered
source. Claims outside authored positives are also validated, so the arm
cannot hide false or incompletely supported edges in surplus output.

There are two distinct proof scopes. **Packet proof** uses the relationship's
own `source_ids`; preserve the historical five R0/R0.4 caller-definition
failures and any other packet deficits. **Session proof** may remap only
byte/hash-validated, actually delivered sources from the *same case* and
rerun the unchanged strict scorer on the same original edge/record. It must
not read extra source during scoring, invent edges, or relabel packet proof.
Report available records, packet-proven links and session-proven links
separately from acquired source and from unobserved task-answer correctness.
Do not accept a run solely because its source spans match gold.

For Rust, do not promote `declared_possible` conditional resolution to
unconditional. Check external module declaration lines, reexport route,
Cargo/workspace/feature control bytes and hashes, visibility, ambiguous
alternatives and hidden/private source before accepting a claim. For calls,
check caller ownership, call-site span, unique import-resolved reference join,
target definition and all support/control intervals. For TypeScript, keep
the scorer's existing generic `uses_type` qualification rather than
claiming a precise subtype. A missing or ambiguous resolver result must stay
an omission/unknown, not an edge.

## Tamper and replay checks

Retain immutable input archives, candidate revision and observer revision,
work manifests, isolated store binding, raw packets, sparse projection,
query trace and phase receipts. Verify their hashes, then independently
recreate snapshots and rerun the unmodified scoring functions. Replay must
compare exact score objects and acquisition trace, not only aggregate totals.

Reject malformed or unknown demand packet schemas independently of the
candidate's validator. Recompute reported byte accounting from the complete
MCP envelope; a truncated or underreported response fails integrity. Run a
small direct negative suite against real claims: remove the final byte
of required caller-definition support from **all** same-case delivered
sources (including duplicates), corrupt a delivered byte or whole-file hash,
change a claimed target/record join, and remove a Rust `mod` or reexport
control interval where applicable. Strict proof must fall while unchanged
source-only acquisition does not turn into semantic credit. Remove/alter a
resolution control hash and verify no exact claim survives; downgrade a
`declared_possible` Rust configuration to `unconditional` and verify the
forbidden configuration probe catches it. Check wrong-file, same-name,
private/hidden, ambiguous-star and unresolved alternatives already present
in the frozen corpus. A missing negative opportunity is reported as
untested, never as a pass. Keep the five historical packet failures visible
even if their separate session proof succeeds.

## Resource boundary and interpretation

For each arm and fresh repetition, retain one-time snapshot setup/index or
file inventory, first semantic question, repeat identical question, warm
cache hit, changed-source invalidation/reparse, discovery, parse, resolve,
source retrieval, continuations, proof packing, serialization and delivery
costs. Count worker and child CPU, elapsed time, peak worker RSS, retained
store/cache bytes, unique/repeated source, complete envelope bytes, discovery
bytes, call counts, overshoot and fraction of snapshot delivered. A zero
semantic index before the first question must be observed, not inferred from
the candidate's label. If a broad scan/parse or all-symbol compilation occurs
on demand, charge it and say so. Use isolated worktrees/stores and fresh
processes as in the current architecture harness; do not access the serving
Loci index. Report shared Anvil snapshot cost once per suite and per-case
warm effects separately. Measure independent proof scoring/replay CPU, RSS
and artifact storage separately from candidate production cost, while
candidate proof construction and delivery remain charged to its worker.
Two repetitions are descriptive, with no cold OS
cache or population claim.

The comparison answers whether this bounded demand mechanism recovers the
targeted source and strict semantic evidence at its measured cost. It does
not establish agent task success, justify production integration, or license
a model campaign. Preserve negative or inconclusive findings as valid
outcomes.
