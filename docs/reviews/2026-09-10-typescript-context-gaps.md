# TypeScript extraction and context-gap reproduction

W2.1.1 is a characterization of the current checkout. The 14 fixtures confirm
both documented export failures, distinguish missing local type relationships
from missing delivery over existing imported-type edges, and expose a false
imported-type edge under generic shadowing. No production implementation was
changed, and this is not the frozen agent outcome baseline.

## Reproduce and inspect

From the isolated `feat/evidence-backed-exploration` worktree:

```sh
UV_CACHE_DIR=.uv-cache UV_PROJECT_ENVIRONMENT=.venv uv sync --frozen --extra dev
.venv/bin/python tests/reproductions/typescript_context_gaps.py --typescript-compiler /opt/homebrew/bin/tsc --output /tmp/typescript-context-gaps.json
```

`--typescript-compiler` is optional for the Loci captures. The recorded packet
includes the additional independent language check using the already-installed
TypeScript 6.0.3 compiler. It runs only against a disposable fixture, with
`--noEmit`; normal indexing invokes no compiler. All indexes and telemetry use
a temporary `LOCI_BASE_DIR`, separate from the shared runtime.

- [Runnable fixtures and capture](../../tests/reproductions/typescript_context_gaps.py)
- [Recorded output](./evidence/typescript-context-gaps-2026-09-10.json)
- Source revision: `6c937ba712540f9c230c7efe66133d22f44e2889`.
- Runtime: Python 3.12.13, Loci 0.2.0, tree-sitter 0.25.2,
  tree-sitter-language-pack 1.15.8, locked worktree-local dependencies.

Each JSON `cases.<name>` retains exact fixture text, file hashes, indexed
symbol IDs/spans, exports, raw/resolved reference records and support, all
materialized edges, search output, selected-source output and bounded graph
retrieval output. `exact_sources` is deliberate diagnostic hydration of all
known fixture symbols, not evidence automatically supplied by search or graph
retrieval. Search-to-get lineage is recorded; diagnostic hydration carries no
false search-selection lineage. Temporary absolute paths are normalized.

The runner completed all 14 cases and the generic language check returned 0.
All Loci fixture indexes reported complete coverage of their supported source
files and `graph_status: healthy`. That status does not mean their semantic
coverage or relationships are correct: known misses and the false edge below
also report healthy. These fixture-scoped observations do not establish
repository-wide absence or language completeness.

## Observed cases and classification

IDs in this table are repository-relative and correspond exactly to the packet.
Reference counts are records; projection may coalesce records into one edge.

| Case key | Exact observation | Classification / consequence |
| --- | --- | --- |
| `imported_interface` | `consumer.ts::__file__#file` → `types.ts::Payload#interface`, one resolved `direct_binding` record and one `references_type` edge at consumer line 2. Both function and interface symbols exist. | Imported interface support works. Function ownership/access and automatic evidence delivery remain separate gaps; detailed controls below. |
| `local_interface` | `consumer.ts::Payload#interface` and `consumer.ts::processOrder#function` exist; no reference observations or semantic edges. | Missing local reference extraction/semantics, not missing endpoints or a failed imported-target resolver. |
| `local_alias_chain` | `Payload#interface`, `First#type`, `Second#type` and `processOrder#function` all exist in `consumer.ts`; no reference observations or semantic edges. | Missing local alias/dependency relationships. The alias declarations themselves are indexed. |
| `imported_alias_chain` | Consumer resolves `Second` to `types.ts::Second#type`; there is no `Second` → `First` → `Payload` chain. | Imported alias endpoint works; local semantic expansion beyond it is missing. |
| `named_type_reexport_chain` | `ImportedPayload` resolves through `PublicPayload` to `types.ts::Payload#interface`, basis `reexport_chain`, retaining the import/re-export/definition support. | Named type re-export/renaming support works. Do not confuse this with following a local type alias definition. |
| `local_heritage` | `Contract`, `ChildContract`, `Base`, `Processor` and `Processor.process` symbols exist; no reference observations or edges. | Missing local heritage observations and class/interface relationships. |
| `imported_heritage` | Three resolved file-owned records: `Contract` at line 2, `Base` and `Contract` at line 3. Projection contains ordinary `references`/`references_type`, not `inherits` or `implements`. | Import binding resolution works; explicit heritage meaning and class/interface source ownership are not represented by these generic references. |
| `same_name_wrong_file` | Both `types.ts::Payload#interface` and `wrong.ts::Payload#interface` exist; the one reference selects only the imported `types.ts` endpoint. | Correct same-name negative control: no repository-wide name guess. |
| `ambiguous_star_exports` | `Payload` exists in both `left.ts` and `right.ts`; the consumer is `unresolved / ambiguous_target`, target null, with no reference edge. | Correct unresolved ambiguity; no selected candidate or completeness guarantee is implied. |
| `generic_shadow` | Three `Payload` records at line 2, columns 30/46/56, all wrongly resolve to `types.ts::Payload#interface`; one `references_type` edge is projected. | False-positive binding/extraction leading to a false proven relationship. A local generic shadows the imported type. Requires repair before comparative baseline measurement. |
| `exported_arrow` | `export const num = ...` has an export record but no indexed `num` symbol. Consumer `num` is `unresolved / ambiguous_target`; only the import edge remains. | Confirmed symbol extraction failure. The reason string alone does not reveal the missing endpoint. |
| `default_identifier` | `number.ts::num#function` exists, but `export default num` produces no export record. Consumer is `unresolved / target_not_indexed`; only the import edge remains. | Confirmed export extraction failure; the declaration endpoint exists, despite the resolver reason wording. |
| `named_function_control` | Inline named function export resolves to `number.ts::num#function`; `references` and `calls` edges exist. | Supported export/control shape. |
| `inline_default_control` | Inline named default function export resolves to the same function endpoint; `references` and `calls` edges exist. | Supported default-export control; isolate the separate identifier-export failure. |

The imported and local cases deliberately use ordinary function declarations.
Neither documented export defect prevents reproducing those cases. An eventual
corpus case whose target is an exported arrow function would lack the target
symbol; a default-identifier import case would lack a resolvable export route.
Both are real preconditions for those common export forms, not a reason to
change independently specified gold context. The final corpus is not frozen
by this packet.

## Existing-edge delivery controls

The `imported_interface` fixture isolates four distinct boundaries:

1. Search for `processOrder` returns the function. Selecting it with `get`
   returns its three source lines, without the interface declaration/body.
2. The question `What dependencies does processOrder have?` with inferred
   anchors is suppressed as `non_relationship_question`. Explicitly providing
   the function or file anchor with that wording gives `no_candidate_endpoint`.
   This is a routing/endpoint-selection limitation, not proof of missing edges.
3. Using `What types does processOrder depend on?` and the file anchor with a
   `references_type` filter returns the existing interface path. Explicit
   file-to-interface seeds do too. Explicit function-to-interface seeds still
   return no path: the reference is owned by the file, not by the function.
4. The successful direct path returns **63 evidence bytes**: the authored
   function-signature line from `consumer.ts:2`. It returns interface identity
   and span metadata, not the interface body containing `amount: number`.
   Deliberate `get(types.ts::Payload#interface)` does return that complete body.

The existing evidence is therefore useful, but it needs selective access from
the retrieved symbol and source hydration. Merely adding a graph call, changing
wording, or counting an existing edge as delivered context is insufficient.
File-owned definition-time references are an intentional existing executable
ownership rule; future type ownership must not casually change runtime-call
semantics. The relevant source is
[`nearest_executable_owner`](../../src/loci/parser/_binding_context.py), which
tests containment in executable bodies, and
[`retrieve_graph_question`](../../src/loci/graph/retrieval.py), which performs
question routing, endpoint selection and authored-line hydration.

All graph requests retain their explicit returned budgets/omissions in the
packet: up to 3 hops, 64 nodes, 8 paths, 32,768 evidence bytes and 8,192 estimated
tokens. These are diagnostic request bounds, not frozen experimental limits.
No number of avoidable reads or agent-success gain is inferred from these
captures. In particular, diagnostic `exact_sources` calls are deliberate
hydration, not measured retrieval misses. The old 38% issue note remains
historical and unbaselined.

## Generic-shadow safety finding

```typescript
import type { Payload } from "./types.js";
export function processOrder<Payload>(value: Payload): Payload {
  return value;
}
```

The imported interface requires `requestId` and `amount`. TypeScript 6.0.3
nevertheless accepts `processOrder(42)` as `number` and `processOrder("ok")`
as `string` under strict checking. The local generic therefore does not refer
to that imported interface. The exact compiler invocation, check source,
version and zero exit code are retained in `generic_shadow_language_oracle`.

Current `_collect_javascript_context` handles declaration names and value
parameters but omits TypeScript generic type parameters. The same file's Swift
collector has separate type-parameter handling; that is a useful contrast,
not authority to copy Swift semantics. The three falsely resolved records
include the generic declaration name itself (bytes 72–79), parameter type
(88–95) and return type (98–105).

Manifest now contains proposed repair
`task_e33ae657f80732bbb90fdba0c0cfd0a7`, **Prevent generic type parameters from
resolving to shadowed imports**, under the active baseline subtree. Its leaf
boundary remains proposed. The comparison-controls task depends on the repair;
independent corpus/gold design can proceed and must retain this negative case.
The two export repairs remain their existing Tasks. This reproduction Task
does not claim any of those defects repaired.

## Unsupported and unmeasured boundaries

- Local type and heritage relationships are absent for the exact fixtures;
  this does not claim that every syntactic TypeScript form was tested.
- Explicit heritage does not enumerate structural compatibility. Structural
  implementers without declarations, conditional/mapped type evaluation,
  complex generic constraints, declaration merging, dispatch, overrides and
  constructor semantics are not exercised or newly supported here.
- The ambiguous star-export case is intentionally unresolved. It does not
  test a bounded candidate API or prove candidate-universe completeness.
- Outputs come from the current public service functions used by the MCP
  wrappers. This packet does not claim a new transport test or host-agent trial.
- Maintained real-repository tasks, gold spans, repeated agent runs, causal
  attribution and comparison budgets remain the subsequent frozen-eval Tasks.

## Source evidence

- [`ISSUES_LIST.md`](../../ISSUES_LIST.md): documented arrow/default export
  failures and historical interface-cascade note.
- [`extract_reference_batch`](../../src/loci/parser/references.py): current
  extraction is import-rooted; local declarations are not a general type graph.
- [`_collect_javascript_context`](../../src/loci/parser/_binding_context.py):
  inspected declaration/value parameter handling and executable ownership.
- [`_reference_validation.py`](../../src/loci/graph/_reference_validation.py):
  projection requires resolved records, so bad binding evidence can still
  propagate a false edge even though the graph passes structural validation.
- [`service.py`](../../src/loci/service.py) and
  [`mcp_server.py`](../../src/loci/mcp_server.py): indexed/search/get/retrieval
  service calls and their MCP wrappers.
- [`retrieval.py`](../../src/loci/graph/retrieval.py): routing at line 832,
  candidate endpoint selection and graph evidence packing.
