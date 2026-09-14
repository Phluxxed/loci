# Multiline TypeScript re-export proof omission

## Confirmed delivered behavior

The `binding_type` capability probe issued `loci_explore` with
`intent=type_dependencies` from
`src/tool-results/service.ts::CaptureCommandResultOptions#type`. It resolved
the import-resolved `uses_type` edge to
`src/work-context/binding.ts::WorkContextBinding#type`, but its relation source
for the barrel was only `export type {\n` at
`src/work-context/index.ts:23` (bytes 587–601). The probe is retained in
`benchmarks/comparisons/ordinary-adoption-v1/runtime/capability-probes.json`,
SHA-256 `70ced72cbbad12c108f5ef31e999105d2ed5331a3b93be5c1f7d7d3f755ac6bb`.

The primary functional check independently repeats the same `loci_explore`
call and the same one-line barrel span, while its separate `loci_file` call
returns the full statement at `src/work-context/index.ts:23-30`, including
`WorkContextBinding` and `WorkContextBindingView`. See
`runs/run-13/functional-check.json`, SHA-256
`6ba2912d583ac2a239b5235181a326da0f15c789f1345da2787add427c38bb87`.
This proves a source-delivery omission, not an incorrect relationship: both
packets select the correct `WorkContextBinding` identity and preserve the
import-resolved edge. The repeated cold-root check has the same omission.

The live `loci_get` contract directs callers to `loci_explore` for complete
import/re-export statements. Therefore the incomplete barrel source is a gap
in the intended `explore` proof path, rather than a requirement to combine
`get` output manually.

## Owning source and cause

The immediate owner is `_Source.support` in
[exploration.py](/Users/brummerv/loci/src/loci/exploration.py:132), SHA-256
`2e507687a889449f56bb7c9d4955470845b698820a185b15a402f745f37ce4a2`.
For a support record it has special declaration-span handling for Go imports
([lines 139-141](/Users/brummerv/loci/src/loci/exploration.py:139)) and Rust
imports/re-exports/modules ([lines 142-143](/Users/brummerv/loci/src/loci/exploration.py:142)), then otherwise falls through to `self.cache.support`
([line 144](/Users/brummerv/loci/src/loci/exploration.py:144)). Relation
bundles pass every record support through this method at
[lines 764-775](/Users/brummerv/loci/src/loci/exploration.py:764).

That fallback is `_CachedSource.support` in
[type_context.py](/Users/brummerv/loci/src/loci/type_context.py:127), SHA-256
`663c099ab8fffc37071f664938c8c4b35df3aa4bee0afe4e1ee72741f858e0cc`.
It deliberately constructs a span from exactly `support.line`
([lines 128-136](/Users/brummerv/loci/src/loci/type_context.py:128)). For this
TypeScript `reexport` record the parser records the opening `export type {`
line, so the generic fallback emits only that marker. No budget omission or
source-hash mismatch occurred: the truncated span itself is accepted into the
explore packet.

## Smallest correction proposal

Add a TypeScript/TSX `reexport` branch in `_Source.support`, beside the
existing Go/Rust branches. It should read the already cached, hash-verified
file and return the unique enclosing `export_statement` span for the support
line, including all lines through its terminating semicolon. If no unique
statement can be identified, preserve the current conservative failure path
(`source_unavailable`) rather than fabricate a span. Leave graph resolution,
edge selection, and output packing unchanged.

The focused acceptance check is one new multiline TypeScript barrel fixture,
such as the run-13 shape: an `export type { ... WorkContextBinding ...
WorkContextBindingView ... } from "./binding.ts";` statement. A
`type_dependencies` result must retain the same import-resolved target and
include one relation source whose bytes and line range equal the full export
statement. Retain the existing one-line re-export proof and stale-cache checks:
the former must remain valid, and changing the cached barrel must still omit
the relation with `source_unavailable`.

Existing coverage overlaps but does not catch this defect. The fixture in
[typescript_context_gaps.py](/Users/brummerv/loci/tests/reproductions/typescript_context_gaps.py:61)
and the assertions in [test_type_context.py](/Users/brummerv/loci/tests/test_type_context.py:75)
use a one-line barrel. The exploration stale-cache check at
[test_exploration.py](/Users/brummerv/loci/tests/test_exploration.py:144)
also uses that one-line fixture. They establish re-export resolution and
hash-safety, but none asserts a complete multiline TypeScript re-export span.
