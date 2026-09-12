# Useful context cases across languages

W4.1 (`task_20015e6a552bcd64cff4d3a003b8ba4d`) defines the source that the next
language slices must deliver. The starting implementation is exploration branch
`60f22c7df320466b23112ba88905fc790ddd98c9`. This is a small implementation target;
it does not claim that those language slices already exist.

The TypeScript product review is complete. Its rejected routing comparison and
all earlier measurements remain unchanged. No additional provider run, reliability
study, repeated completed batch or new benchmark platform is part of this task.

## Language capability matrix

“Existing” below means the bounded implemented subset, not complete language
semantics. All four new language slices still need contract expansion; existing
import/reference/call records alone do not deliver it. Exact source inspections
and the input check are recorded below.

| Language | Existing search/get and graph support | Required new context | Explicit limits |
| --- | --- | --- | --- |
| Python | Functions/classes, lexical import aliases, contained import-rooted references and definite local/imported calls | Authored annotations; explicit `TypeAlias` aliases; bounded generic arguments; bare/dotted literal forward names; direct class bases; incoming authored users | No annotation evaluation, module import/execution, computed bases, MRO, Protocol/ABC satisfaction or runtime type/dispatch inference |
| Plain JavaScript | Functions/classes, named arrow/default exports, contained ESM import/re-export references and definite calls | Selected value/call dependency definitions and direct class-extends source, with complete origin proof | No TypeScript structural types, JSDoc type extraction, computed imports/callees/bases, CommonJS member inference, prototype mutation or runtime dispatch |
| Go | Function/type declarations, declared package identity, contained module/workspace/replacement imports, exported package-qualified references and definite calls | Alias versus defined-type source; signature/field/generic argument and constraint uses; explicit struct and interface embedding; incoming authored users | No implicit interface satisfaction, inferred method sets, promoted-member dispatch, active build/cgo selection, ambient caches or dependency fetching |
| Rust | Function/struct/trait/impl declarations, declared Cargo/module/visibility routes, contained import/re-export references and definite calls | Aliases; authored type uses and generic bounds; supertraits; explicit impl-site-to-trait and impl-site-to-self-type source; incoming authored users | No trait-object dispatch, monomorphization, inferred implementing set, macro/generated-code expansion, active-feature guesses, Cargo/rustc execution or crate fetching |
| TypeScript/TSX control | The existing TypeScript authored-type/heritage and exploration slice, with seventeen pinned v3 cases | Retain those contracts and repair the newly exposed JSX-bearing TSX anchor miss in W4.6 | Existing generic-shadow and ambiguous-export negatives remain; JSX does not itself prove a repository call |
| Markdown control | Ordinary heading/section search and exact source retrieval | Preserve nested-section spans, peer boundary and UTF-8 text | No programming-language type/impact semantics are imposed on Markdown |

### Authored syntax boundaries

Python supports bare and qualified names through uniquely proven lexical or
contained import/re-export bindings, direct `Alias: TypeAlias = Target` aliases,
generic argument names inside authored subscripts such as `list[P]` or
`tuple[Span, ...]`, and direct named class bases. Literal forward references are
unescaped string literals containing only a bare/dotted name. Compound strings
such as `"list[P]"`, calls, dynamic rebinding and wildcard ambiguity stay
unproven. Builtin/typing markers do not become repository targets. Type-parameter
binders shadow module types; ordinary function parameters must not incorrectly
shadow names in their own definition-time annotations. PEP 695 type-parameter
binding is a negative control here; arbitrary generic evaluation and additional
alias spellings are outside this first slice.

JavaScript's dependency request follows definite calls and supported imported
value references, including named/namespace bindings and contained ESM re-exports,
and direct `class Worker extends Parent`. Method bodies retain their own owners.
The positive plain `.js` cases include a named arrow, a default identifier export
and a re-export chain. Star-export ambiguity and failure to forward default are
separate negative facts. Existing import records remain dependency evidence;
an import alone does not invent a callable or type edge.

Go supports named local/package-qualified types in signatures, aliases, fields
and generic arguments/constraints, plus explicit struct/interface embedding.
`AliasID = UserID` and `UserID int64` remain different authored declarations.
Type parameters and builtin/approximation/union terms do not become guessed
repository targets. The source unit is the complete Go type specification,
including `=` where authored, rather than its enclosing shared `type` keyword.
Dot/blank imports retain import information without invented symbol references.
Supported controls keep the declared package name and the exact `go.mod`,
`go.work` or contained replacement route; unrelated same-name packages cannot
repair a missing endpoint.

Rust supports named local/contained imported types, type aliases, generic type
arguments and bounds, direct supertraits, and explicit `impl Trait for Type`
sites. An impl site points separately to its trait and self type; it retains its
own exact source owner. A bound is not an impl, and an impl is not a call target.
Keep namespace/visibility ambiguity and type-parameter shadowing explicit. The
optional contained workspace dependency case requires `declared_possible`, while
the ordinary module case is `unconditional`; neither chooses an active build.
Divergent cfg routes never become a single exact endpoint. Standard-library and
external crate types are not fetched to fill missing context.

### Source evidence and observed starting gaps

The shared gate is visible in `src/loci/exploration.py:201-322`: locate emits
source, impact traverses incoming supported calls/references, and dependency
expansion stops with `unsupported_language` outside TypeScript. Import edges
are not currently included in impact. Declaration extraction is in
`src/loci/parser/extractor.py:28-69,698-769`; the language map is in
`src/loci/parser/languages.py`. Exact-call acceptance joins local callables or
resolved imported references in `src/loci/graph/calls.py:558-674`.

Language-specific evidence:

- Python alias/qualified-member and failure boundaries:
  `tests/graph/test_references.py:1506-1692`; imported call proof:
  `tests/graph/test_calls.py:740-854`.
- JavaScript origin/re-export and ambiguity boundaries:
  `tests/graph/test_references.py:1134-1478`; named arrow and default-identifier
  endpoints: `tests/test_exported_arrow_functions.py:176-224` and
  `tests/test_default_identifier_exports.py:28-116`.
- Go package/module/workspace identity: `src/loci/graph/go_modules.py:158-271`
  and `src/loci/graph/imports.py:835-896`; contained exported-reference proof
  and negatives: `tests/graph/test_references.py:851-1131`.
- Rust Cargo/module routes: `src/loci/graph/_rust_resolution.py:487-619,852-900`
  and `src/loci/graph/_rust_references.py:281-332`; conditional/convergent
  versus ambiguous and unsupported references:
  `tests/graph/test_references.py:338-409,708-808`.
- Markdown section source and TSX imported-reference/call observations:
  `tests/parser/test_markdown.py:75-85`,
  `tests/parser/test_references.py:511-525`, and
  `tests/parser/test_calls.py:431-444`. These observations do not guarantee
  that every JSX-bearing source declaration is indexed.

The source-only input check at the starting commit finds four missing expected
declarations: Python's `Alias`, Go's `AliasID`, Rust's `UserId`, and the TSX
`Badge` function. The aliases are explicit W4.2/W4.4/W4.5 extraction targets.
For TSX, the suffix maps to the TypeScript grammar and the JSX-bearing function
is not extracted; W4.6 must repair and verify that demonstrated retrieval defect.
The existing controls and all historical outcomes remain intact. Corpus integrity
passing means the expected bytes and answers are coherent, not that these
currently missing declarations or new semantic relationships already pass.

## What a context request must do

| Question | Required behavior |
| --- | --- |
| Locate | Find the named or described declaration and return its exact source. Ordinary search/get remains available for every indexed language and Markdown. |
| Contract/dependencies | Return the authored declarations needed to understand the selected function or type, together with every source span proving their origin and relationship. JavaScript supplies value dependencies and direct class bases rather than imagined annotations. |
| Known impact | Follow supported incoming static relationships. Keep the original edge direction and identify traversal direction separately. Report known callers/type users, with exact source and proof; never imply complete runtime impact. |

These are task meanings, not a demand for identical relationship names across
languages. The current `type_dependencies` intent only expands TypeScript.
The language implementations and W4.6 must expose the behavior above through the
shared interface, retaining existing TypeScript requests. An empty successful
JavaScript type result does not satisfy a dependency question. Renaming a tool
or adding an intent alias by itself does not deliver the required context.

Relationship certainty comes from the authored source and binding evidence.
Query relevance may select or omit a proven relationship; it cannot strengthen
an uncertain one. Deliver complete required declarations and import/re-export
support before claiming complete context. Keep unresolved, ambiguous, external,
unsupported and budget-limited outcomes distinguishable. Same-name declarations
in another file, scope, package or namespace are never substitute evidence.

## Delivery and evidence budgets

Every new case uses the same limits. These reuse the current exploration defaults
inside the existing observed-retrieval ceilings; they are not tuned per language.

| Bound | Limit |
| --- | ---: |
| Search results / explicit anchors | 5 / 5 |
| Dependency hops / default impact hops | 3 / 1 |
| Nodes examined / selected items / neighbors per node | 64 / 12 / 32 |
| Exploration source evidence / complete serialized output | 8,192 / 16,384 UTF-8 bytes |
| Any individual retrieval operation: source / full output | 16,384 / 32,768 UTF-8 bytes |
| Whole task: delivered source / full output | 131,072 / 262,144 UTF-8 bytes |
| Whole task: observed retrieval calls | 24 |
| Retrieval operation / whole task time | 10 / 180 seconds |

The whole-operation ceiling includes exact get and fallback reads. The entire
model-visible payload counts, including selection explanations, support,
diagnostics, accounting and errors. Repeated source delivery counts repeatedly
toward cost. Source recall is measured by unique exact required byte intervals.
Metadata, a correct target ID or an undelivered source path cannot earn source
credit. Estimated evidence tokens remain estimates, separate from provider usage.

The normal positive cases must deliver all required context inside those bounds.
A deliberately reduced evidence limit, including zero, must produce truthful
omissions rather than fabricated completeness. Such a bounded response can pass
the trust check while failing full context delivery. Clipped source only earns
its actual delivered byte coverage. Traversal terminates on cycles and declares
node, hop, neighbor, item and byte exhaustion.

## Inputs and later comparison

The sibling [corpus](../../benchmarks/corpora/multilingual-context-v1/README.md)
contains small source snapshots, exact source/hash expectations and independent
answer facts. Its case and source hashes are fixed before implementation. Only
materialized source snapshots and ordinary task prompts may reach a task agent;
answers, context lists, forbidden relationships and evaluator labels stay outside
the agent's filesystem, tool responses and prompt. Authoring fixtures does not
count as language delivery passing.

Reuse `benchmarks/typescript_context_corpus.py` for source integrity,
materialization and exact answer facts, and the existing delivery/observed-trace
accounting for exact spans, relationships and total retrieval cost. The existing
adapter's TypeScript-specific relationship mappings will need a bounded extension
for the declared language meanings. That is part of implementation/measurement
integration, not a new runner architecture.

W4.2-W4.5 implement and check each language. W4.6 checks their shared interface,
freshness, source proof and budget behavior. W4.7 pins the actual implementation,
effective schema, model/provider setup, prompt, schedule and final scorer before
any outcomes. Verify the scorer against real tool outputs, including a wrong
origin and missing support, at that point. Preserve the original cases; a
necessary source/gold correction gets a new corpus version with its reason.

For each language compare an exact-retrieval workflow with the delivered context
workflow on the same pinned source and task prompts under equal budgets. Report
required-context recall, unsupported relationship claims, exact task success,
all observed tool calls, total output/source bytes, provider input tokens and
latency separately. Include failures, fallback/helper calls and recoverable
errors in cost. Report fixture results separately from repository-work questions.
Do not equate a synthetic contract-comprehension task with successful code editing
or universal usefulness. Preserve unsuccessful/null comparisons and record a
practical per-language delivery decision; there is no automatic retry-until-pass.

TypeScript's existing seventeen-case v3 corpus and its published outcomes remain
immutable regression controls. The new corpus adds a TSX source control and an
ordinary Markdown navigation control. Their identities are pinned with the new
inputs; no historical measurements are rescored or pooled with future ones.
