# W2.3.1 — Type observations and proven relationships

Date: 11 September 2026. Objective: `obj_0110c8712b21bdd2c12532f189d84a74`.
Task: `task_1a4b33f09d0ec97e6cb7f08ea50cf89f`.

This is the implementation contract for W2.3 on
`feat/evidence-backed-exploration`. It follows the completed
[W2.2 comparison and residual evidence](../../benchmarks/results/typescript-context-existing-v1/residuals.md).
The canonical work graph remains in `/Users/brummerv/loci`; this isolated code
checkout carries no active copy of it. The contract is a design decision within
Vik's authorization to implement W2.3, not a claim that its implementation or
the later comparison has passed.

## Purpose and module interface

Add one TypeScript relation family beside imports, imported-symbol references,
and calls. Its module hides extraction, binding resolution, validation and graph
projection behind typed observations and the existing generic graph interface.
Each family keeps its own payload and validator. There is no universal-record
migration and no change to runtime-call or existing file-owned reference meaning.

An observation records authored syntax. Resolution proves the identity of its
owner and target within a declared scope. Projection makes only fully justified
relationships traversable. Source delivery remains a separate decision: W2.2
showed that a real dependency can still be unnecessary or repeated context.

## Meaning, direction and certainty

| Relation | Source → target | Meaning |
|---|---|---|
| `uses_type` | declaration owner → named declaration used in its type expression | An authored contract depends on the named declaration. A `typeof` use can target a value declaration. |
| `extends` | derived class/interface → named base declaration | The source explicitly names the target in an extends clause. |
| `implements` | class → named implemented declaration | The source explicitly names the target in an implements clause. |

All edges use namespace `loci`. A same-file lexical target has resolution `exact`;
a target justified by a contained import/export route has `import-resolved`.
These tiers qualify target identification. They do not mean that TypeScript
accepted the declaration, that a class satisfies every structural requirement,
or that a call dispatches to a particular method. No inferred implementation,
override, construction, receiver or dispatch edges are introduced.

Repeated sites remain separate records. Projection deduplicates by relation,
source and target, retaining deterministic first-site evidence; the records
retain every exact occurrence. Existing `references_type` records and edges
keep their original identity and meaning. A new declaration-owned `uses_type`
edge is distinct from that existing imported-reference relation.

Recursive `uses_type` self-edges require a validated self-reference observation.
Self heritage remains unresolved. Cross-declaration authored cycles need no
recursive resolution and do not claim program validity; generic traversal keeps
its visited-node and hop limits.

## Observation and ownership

`RawTypeObservation` carries these explicit fields:

| Fields | Contract |
|---|---|
| `source_file`, `language`, `source_hash` | Normalized repository-relative source, `typescript`, full-file SHA-256. |
| `line`, `column`, `start_byte`, `end_byte`, `text` | One-based location and exact nonempty UTF-8 byte interval. `text` is precisely those bytes. |
| `path` | Named head, or a bounded qualified head; empty only for explicitly unsupported syntax. |
| `relation`, `context`, `lookup_space` | Relation above; authored role (annotation, return, property, alias, type argument, constraint, type query or heritage); type or value lookup. |
| `owner` | `TypeDeclarationOwner`: declaration kind and exact indexed declaration span, or the actual unindexed declaration span. |
| `local_bindings`, `import_bindings` | Bounded nearest-scope lexical evidence and unchanged `ImportBinding` records. |
| `binding_state` | Local, imported, shadowed, ambiguous, unbound or unsupported. |
| `candidates_complete`, `candidates_truncated` | Whether raw binding candidates exhaust the declared scope and how many were omitted. |
| `unsupported_reason` | Explicit reason for unsupported syntax; null for supported syntax. |

The occurrence interval is the authored target name or qualified head. Generic
arguments are separate `uses_type` occurrences. Broader syntax is recoverable
from the cached source and its context; a dynamic heritage expression is retained
as one unsupported expression rather than split into guessed targets.

Declaration ownership is separate from executable-body ownership:

- Parameter and return annotations belong to their function or indexed method.
- Class fields belong to the class; interface properties and method signatures
  belong to the interface, whose contract contains them.
- Alias RHS expressions, including nested function types, belong to the alias.
- Heritage and declaration-level generic constraints/defaults belong to the
  declaring class, interface, alias or function.
- Named arrows use their indexed declaration span, accounting for the variable
  declarator and export wrapper. A nested declaration keeps its own ownership.
- An anonymous executable or unsupported declaration cannot donate its type
  observations to the nearest outer indexed declaration. Unknown, missing and
  ambiguous owners remain unresolved; there is no file-node fallback.

`LocalTypeBinding` retains name, declaration kind, type/value/both namespace,
declaration byte interval and lexical-scope interval. Resolution joins the
declaration evidence to exactly one indexed endpoint. A missing local endpoint
does not permit fallback to an import or a wider same-named declaration.

## Supported first-language scope

The first extractor recognizes authored parameter, return, property and alias
uses through named, generic, union, intersection, array, tuple, indexed-access,
`keyof` and function-type syntax. Generic heads, arguments, constraints and
defaults are independent occurrences; primitive keywords are not dependencies.

Local ordinary type names resolve to uniquely bound interface, alias, class or
enum declarations. A bare `typeof` name uses value lookup and can resolve an
indexed constant, function, class or enum; this is a compile-time dependency,
not a runtime read or invocation. Generic parameters shadow type names within
their declared scope and remain explicitly unresolved as type parameters.
They do not shadow the same spelling in value-space type queries. Unrelated
value declarations do not hide a type-space binding.

Imported targets reuse existing contained import resolution and JavaScript
export surfaces, including named re-export provenance. Ordinary and type-only
imports can supply annotations when the target has the required namespace.
A symbol import permits no extra member suffix. A namespace import permits
one exact exported member. Qualified suffixes are never silently discarded.
Wrong-file names and ambiguous star exports cannot become exact targets.

Class extends supports an authored direct class binding. Interface extends and
class implements support an exact named interface, class or alias declaration;
the alias remains the authored endpoint, without computing its resulting type.
Local/imported, qualified and generic heads and multiple interface clauses retain
their distinct sites. A type-only route cannot justify the value required by a
class extends clause. When the existing export evidence cannot establish that
value route, the outcome remains unsupported rather than optimistic.

Mapped, conditional, inferred, template and import-type computations, namespace
augmentation/merging, ambient cross-file declarations, dynamic mixins, computed
heritage and unsupported owners retain explicit unsupported outcomes where
encountered. No whole-program type inference, structural compatibility search,
repository-wide bare-name lookup, external package inspection or other-language
type extraction is claimed.

## Resolved records and candidate policy

`TypeRelationRecord` retains the raw observation, optional source and target
identities, `status`, `unresolved_reason`, `resolution_basis`, `support`,
`resolution_controls`, `candidate_universe`, `candidate_scope_file`,
`candidate_ids`, `candidates_complete` and `candidates_truncated`.

The declared target universe is either the observation's nearest lexical scope,
one proven imported module's supported export surface, or unavailable. The raw
path and binding intervals identify the lookup within that universe. Candidate
completeness never means complete repository or TypeScript coverage. Imported
surface ambiguity or its internal bound cannot claim a complete enumerated set;
unknown and external universes remain unavailable/incomplete. Raw binding limits
also propagate into the resolved record's candidate metadata.

A resolved record requires exactly one source owner and compatible target,
complete singleton target candidates, zero truncation and a justified basis:
`lexical_binding`, `direct_binding`, `qualified_member` or `reexport_chain`.
Unresolved records have no final target or resolution basis and retain their
specific reason and any bounded candidate evidence. Even a singleton candidate
is not an edge when its universe is incomplete. Candidate IDs are diagnostic
data only and never enter exact or heuristic graph reachability.

`TypeSupport` carries kind, file, line, hash and optional endpoint identity for
the type site, owner, definition, import binding and local/re-export steps.
`TypeControl` carries the exact control path and hash. Resolved records require
site, owner and target-definition support, plus the binding/export route when
imported. Missing, stale, malformed or internally inconsistent support is a
contract error, not an unresolved semantic result.

Limits are 16 path segments, 16 binding/target candidates per observation and
100,000 observations per file. Binding truncation is explicit and cannot produce
an edge. Exceeding the per-file observation limit aborts that family's extraction
with a diagnostic; indexing must not silently retain a seemingly complete prefix.
Existing export-surface bounds and generic retrieval budgets still apply.

## Persistence, validation and integration

Add `GraphIndexState.type_relations` using the existing index storage. Increment
persisted graph schema 12 to 13 and extractor version 24 to 25; keep public graph
schema 1. Old or malformed state follows the existing rebuild policy. Other
family payloads keep their schemas and validators.

Unchanged source can reuse raw observations. Every rebuild still resolves them
against the current complete symbol/import/export sets and configuration, so
target additions, removals, source edits and control changes replace stale
outcomes. Source, owner, target, support and control hashes are cross-checked.
The family validator re-establishes the expected pure resolution from the retained
binding evidence and current indexed records before accepting persisted edges.

Use the existing graph neighbors, traversal, paths, retrieval and health
contracts. Expose relation meaning, unresolved diagnostics and repeated-site
evidence through additive generic output where needed; do not introduce a
parallel type-only query tool. Semantic bridge policy respects stored direction
and relation kind. Opt-in source hydration can follow accepted new relations
under its existing bounds; default exact get remains unchanged.

Concretely, the existing `loci_graph_references` operation gains
`family="type"` for the new paginated records; its default `family="symbol"`
keeps the current imported-reference response. Type results identify their
family and retain full typed observations, candidate metadata and support.
Index and graph-health output add type counts, resolution bases and unresolved
reasons. Opt-in get marks new relation delivery with scope
`declared_type_relations`; stored edge identity and support remain visible.

W2.3 acceptance includes valid and invalid record round trips, exact source
ownership and target fixtures, generic/shadow/ambiguity negatives, real
source/target/configuration invalidation, bounded graph queries, persisted source
hydration and actual MCP output. Import/reference/call controls must retain their
behavior. Frozen W2.1/W2.2 artifacts and comparison methods stay unchanged; a new
agent comparison and broader delivery-selection work belong to later tasks.

## Checked scenarios and source evidence

The concrete acceptance cases motivating these decisions are:

- `processOrder(value: Second)` → `Second` → `First` → `Payload`, preserving
  both function ownership and the authored intermediate aliases.
- `Processor extends Base implements Contract` produces distinct class-owned
  extends/implements records; `ChildContract extends Contract` is interface-owned.
- `processOrder<Payload>(value: Payload)` does not reach the imported `Payload`.
- A local `TemporalView` alias using `(typeof TEMPORAL_VIEWS)[number]` depends
  on that value declaration through a type query, without inferring its type.
- Renderer and retrieval-result properties/intersections reach the named local
  declarations. The existing helper call remains a call, and a real but
  unnecessary `TemporalQuery` dependency remains a later selection concern.

Repository evidence was inspected at parent commit `ce5fd89`:
`parser/_binding_context.py`, `parser/_javascript_bindings.py`,
`graph/_javascript_references.py`, `graph/_reference_validation.py`,
`graph/contracts.py`, `graph/state.py`, `graph/materialize.py`, and
`service.py::_index_repo_unlocked`, alongside the frozen residual packet above.
Existing annotation ownership and imported-only resolution explain why a new
family is needed; existing persistence and export support explain what it reuses.

The bounded language research was checked against official documentation on
11 September 2026. TypeScript distinguishes type, value and namespace declarations;
classes/enums supply both type and value, while interfaces/aliases supply types.
[Declaration merging](https://www.typescriptlang.org/docs/handbook/declaration-merging.html#basic-concepts).
The type operator `typeof` refers to value declarations in type expressions.
[Typeof type operator](https://www.typescriptlang.org/docs/handbook/2/typeof-types.html).
An `implements` clause asks the compiler to check compatibility; Loci records
the authored clause without performing that check.
[Class heritage](https://www.typescriptlang.org/docs/handbook/2/classes.html#implements-clauses).
Type-only imports cannot supply a class's runtime extends expression.
[Type-only imports and exports](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-3-8.html#type-only-imports-and-export).
The conservative supported subset and record layout above are Loci design
decisions, not claims that the language itself has those limitations.
