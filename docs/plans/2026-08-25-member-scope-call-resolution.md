# Plan: Member-Scope Call Resolution

**Status:** in progress on `swift-graph-support`; Tasks 1-3 implemented.
Tasks 4-8 re-verified against the code on 2026-08-25 — see **Plan Audit**.

**Date:** 2026-08-25

**Governing design:**
`docs/design/2026-07-13-extensible-graph-retrieval-design.md`

**Accepted prerequisite:**
`docs/plans/2026-07-20-extensible-graph-retrieval-stage-11-trustworthy-calls.md`

**Blocks:**
`docs/plans/2026-08-24-swift-graph-support.md` (`swift-modules`, `swift-resolve`)

## Goal

Raise call-edge yield across every supported language by giving loci two
concepts it does not currently have:

1. **Deferred callable visibility** — a call inside a function body can see a
   sibling callable declared later in the same scope.
2. **Member scope** — a call inside a type body can see that type's members,
   and a call written as a bare type name can reach that type's initializer.

Both are lexical and exact. Neither introduces receiver type inference,
repository-wide name matching, or any heuristic tier. The trust rules frozen in
Stage 11 stand unchanged; this plan widens what can be *proven*, not what
counts as proof.

## Plain-language Outcome

Today loci resolves a call only when the callee is a bare name bound either by
an import or by a function defined *earlier* in the same file. That is a much
smaller slice of real code than it sounds. Two very ordinary shapes fall
outside it: calling a helper defined further down the file, and calling a
method on the type you are already inside. After this work, both resolve, and
constructing a type by name (`Widget(...)`) resolves to that type's
initializer.

The effect is largest in Swift, where nearly all code is written as methods on
types, but the mechanism is missing in Python, JavaScript, TypeScript, Go and
Rust too.

## Authorization and Review Posture

Each task needs Vik's explicit go before implementation. Work proceeds task by
task, tests first, on `swift-graph-support` — this is part of the Swift graph
work, not a separate line of development. The branch stays unpushed until the
whole language ships as one coherent unit.

## Plan Audit — 2026-08-25

Tasks 1-3 were implemented, and Task 3 contradicted this document's own
contract section. The cause was a method error worth naming: the contract
claims were written by reading type definitions in isolation, without tracing
the values they describe into their callers. `CallResolution` was read in
`graph/calls.py` without following `record.resolution` into
`materialize_call_edges` and out to `GraphEdge.resolution`, which is the
graph-wide `ResolutionTier`.

Every remaining claim has now been re-checked against the code and, where it
asserted a payoff, re-measured. Four were wrong; they are corrected in place
below and listed here:

1. **A new resolution tier was never the right lever** (Task 3, corrected).
2. **The bare `Uppercase(...)` and `Type.member()` buckets are shape counts,
   not payoffs.** Measured same-file yield is 953 and 220 sites respectively,
   against 44,196 and 9,334 observed. Tasks 5 and 6 are close to worthless
   until Swift module resolution exists.
3. **`EXTRACTOR_VERSION` is not a Task 7 concern.** Persisted graph state is
   re-validated against the current resolver on every graph read, so *any*
   resolver change invalidates existing indexes. Proven by feeding a
   pre-Task-3 record to `validate_call_records`, which rejects it with
   `Resolved call outcome does not match current local/reference evidence`.
   Task 3 therefore carries a bump to `EXTRACTOR_VERSION = 16`.
4. **`_swift_path` is shared with Stage 10 reference extraction**
   (`parser/references.py:402`), so Task 4 changes reference output too.

## Measured Baseline

Measured 2026-08-25 by running `extract_import_batch` directly over each corpus
and tallying `callee_form` and `local_binding_state`. Swift corpus is
`~/work/references/lott-ios`; Python corpus is loci's own `src/loci`.

### Swift — 4,410 files parsed, 126,406 call sites

| Callee shape | Sites | Share |
|---|---:|---:|
| identifier, no binding found | 60,112 | 47.6% |
| identifier, definite binding | 592 | 0.5% |
| identifier, shadowed | 2,448 | 1.9% |
| identifier, ambiguous | 18 | 0.0% |
| static path (`a.b()`) | 41,310 | 32.7% |
| dynamic (no static path recoverable) | 21,926 | 17.3% |

Only the 592 definite-binding sites can currently produce an `exact` edge.

### Swift — where the 101,422 unresolvable sites actually live

These are **shape** counts. They say how call sites are written, not how many
could be resolved, and the original version of this plan wrongly read them as
payoff estimates.

| Bucket | Sites | Share |
|---|---:|---:|
| bare `Uppercase(...)` — initializer calls | 42,766 | 42.2% |
| static path, non-type head (`obj.method()`) | 32,533 | 32.1% |
| bare `lowercase(...)` — module or member calls | 17,346 | 17.1% |
| static path, `Type.member()` | 8,777 | 8.7% |

`self.foo()` does not appear as a static path because `_swift_path` returns
`None` for a `self` target — `self` parses as `self_expression`, not
`simple_identifier` — so those sites are classified `dynamic` today.

### Swift — how much of that is reachable without cross-file resolution

Measured 2026-08-25 by walking every Swift tree and checking each callee
against the symbols parsed from *that same file*.

| Shape | Observed | Target declared here | Same-file resolvable |
|---|---:|---:|---:|
| bare `Uppercase(...)` | 44,196 | 5,130 | **953** |
| `Type.member()` | 9,334 | 962 | **220** |
| `self.member()` | 2,084 | 2,084 | **1,410** |

The gap between "declared here" and "resolvable" is types with no explicit
`init` (4,177 sites) and heads whose named member is not in the file (742).
Swift structs mostly use the implicit memberwise initializer, which produces no
`Type.init` symbol, so `Widget()` correctly stays unresolved.

The 39,066 bare-uppercase sites naming a type declared *elsewhere* are led by
`XCTAssertEqual` (9,153), `XCTAssertTrue` (2,453) and `XCTFail` (773) — which
are not constructors at all but global XCTest functions. That bucket is a
module-resolution problem, not an initializer problem.

### Swift — what the 21,926 `dynamic` sites actually are

| Callee shape | Sites |
|---|---:|
| `foo().bar()` — navigation off a call result | 10,536 |
| `.foo()` — leading-dot implicit member syntax | 4,645 |
| navigation off another unresolvable navigation | 2,231 |
| `self.foo()` | 2,084 |
| `super.foo()` | 1,268 |
| `try x.foo()` | 535 |

Only the `self` row is in scope. Everything above it needs receiver type
inference or contextual typing; `super` needs inheritance. Task 4 therefore
addresses 2,084 of these sites, not the whole bucket.

### Python — 55 files, 9,334 call sites

| Bucket | Sites | Share |
|---|---:|---:|
| bare `lowercase(...)`, no binding | 4,858 | 59.7% |
| static path, non-type head | 2,641 | 32.5% |
| bare `Uppercase(...)` | 454 | 5.6% |
| static path, `self.x()` | 121 | 1.5% |
| static path, `Type.x()` | 59 | 0.7% |

The Python bare-name bucket is dominated by true builtins (`len` 521,
`isinstance` 511, `tuple` 272) which must stay unresolved — but it also
contains same-file module-level helpers: `_error` 322, `_unresolved` 61,
`_nonempty_string` 55, `_node_text` 53.

## Root Cause 1 — Callable bindings are not visible before their declaration

`src/loci/parser/_binding_context.py:381` binds a Python `function_definition`
with `active_start_byte=node.end_byte`. `_local_call_binding`
(`src/loci/parser/calls.py:264`) then filters to bindings where
`active_start_byte <= callee.start_byte`. A call textually before the
declaration therefore sees nothing.

Reproduced minimally:

```python
def early():
    return 1

def caller():
    a = early()   # definite  -> resolves
    b = late()    # absent    -> does not resolve
    return a + b

def late():
    return 2
```

That is correct for a call evaluated at module import time and wrong for a call
inside a function body, which does not execute until after the whole file is
loaded. Every supported language has the same property, and
`ExecutableOwner.kind` already distinguishes the two cases: `file` owners
execute in source order, `callable` owners do not.

Every one of the 72 `_error(...)` call sites in `src/loci/graph/calls.py` is
`absent` for this reason alone.

## Root Cause 2 — There is no member scope

`RawCallSite` carries `local_candidates` drawn only from `SyntaxContext`
lexical bindings, and the contract in `src/loci/parser/call_models.py` actively
forbids anything else:

- `"only identifier calls can carry local candidates"` — a `static_path` callee
  can never carry one.
- `"static path calls must use absent local binding state"`.
- `"local candidate name must match the callee root"`.

So `self.render()` and `Widget.make()` are structurally incapable of carrying a
resolvable candidate no matter what the collector observes. Separately, the
Swift collector deliberately skips members: `_collect_swift_context` excludes
declarations inside `_SWIFT_MEMBER_SCOPES` from file-scope callable bindings,
because binding `run` as a bare file-scope name would be wrong.

Both decisions are right. What is missing is a second, differently-keyed
channel: a candidate qualified by its owning type.

## Root Cause 3 — Type names are not callable targets

`Widget(...)` is 42.2% of Swift's unresolvable sites by shape. The callee is a
type name, and the target is that type's initializer. Symbols already carry
what is needed — `parse_file` yields `Widget.init` as a `method` symbol with a
`Type.member` qualified name, for `class`, `struct` and `enum` alike — but
nothing joins a bare `Widget` callee to `Widget.init`.

The measured same-file yield is 953 Swift sites and 41 in loci's own Python.
This root cause is real but small on its own; it becomes valuable only once a
type name can be resolved across files.

## Scope

### In scope

1. Deferred callable visibility for `callable`-owned call sites, all six
   languages.
2. Member-scope candidates for calls inside a type body, reached either by
   implicit self (bare name) or explicit `self` / `this`.
3. `Type.member()` where `Type` resolves to an indexed type in the same file or
   through an import binding.
4. Type-name calls (`Widget(...)`, `Widget()`) resolving to that type's
   initializer where the language has one and it is indexed.
5. Swift `self` callee paths, currently discarded as `dynamic`.

### Explicitly out of scope

- **Receiver type inference.** `obj.method()` where `obj` is a local of
  inferred type is 32.1% of Swift's unresolvable sites and 32.5% of Python's.
  It requires a type system. It stays unresolved and is not a heuristic tier.
- Protocol and interface dispatch — a call to a protocol requirement has no
  single provable target.
- Inheritance and superclass member lookup.
- Extensions in other files contributing members to a type.
- Any repository-wide name match.

## Contract Changes Required

These are additive to persisted models and therefore need an
`EXTRACTOR_VERSION` bump (currently `13` in
`src/loci/storage/index_store.py`) and a schema review.

### `src/loci/parser/call_models.py`

- New `member_candidates: tuple[MemberCallableBinding, ...]` on `RawCallSite`,
  independent of `local_candidates`, permitted on `identifier` and
  `static_path` callee forms.
- New `member_binding_state: CallBindingState`.
- New `MemberCallableBinding` carrying the owning type's declaration range and
  qualified name alongside the member's own definition range.
- Relax `"only identifier calls can carry local candidates"` to apply to
  `local_candidates` only; keep `local_candidates` exactly as strict as today.
- Keep `"static path calls must use absent local binding state"` for
  `local_binding_state`.

### `src/loci/parser/_binding_context.py`

- `LexicalBinding` gains `deferred_visible: bool`, set for Python callable
  declarations only, meaning "visible to a call site whose owning definition is
  nested inside this binding's scope, regardless of `active_start_byte`".
  *(Done in `b8bac76`.)*
- New member-scope collection per language, keyed by owning type declaration
  rather than by lexical scope.

### `src/loci/parser/calls.py`

- `_local_call_binding` honours `deferred_visible` via
  `_visible_to_deferred_call`. *(Done in `b8bac76`.)*
- New `_member_call_binding` producing `member_candidates`.
- Swift `_swift_path` returns a path for `self`-rooted navigation instead of
  `None`. Note that this function lives in `parser/_reference_paths.py` and is
  shared with `parser/references.py:402`, so the change alters Stage 10
  reference observations as well as calls.

### `src/loci/graph/calls.py`

- ~~`CallResolution` gains `"member-resolved"`~~ — **wrong, see Plan Audit.**
  `CallRecord.resolution` is passed straight into `GraphEdge.resolution`
  (`_call_validation.materialize_call_edges`), which is the graph-wide
  `ResolutionTier` shared with import, reference and contains edges and
  filtered on by `SAFE_GRAPH_RESOLUTIONS`. Member calls carry the same proof
  strength as local ones, so they stay at the `exact` tier and are
  distinguished by basis alone. `CallResolutionBasis` gains
  `"member_callable"` and, in Task 5, `"type_initializer"`.
- `_resolve_call` gains a member branch, ordered after `_local_target` and
  before the imported-reference branch, and must fail closed with
  `conflicting_resolution` when both a local and a member target survive.
- `_validate_outcome` gains a member arm mirroring the `exact` arm's evidence
  requirements: the target must be an indexed callable, and the support must
  carry the member definition site.
- New unresolved reasons: `member_target_not_indexed`,
  `member_binding_ambiguous`.

## Known Complication — a type is not one symbol

`parse_file` on `tests/fixtures/sample.swift` emits **two** symbols with
qualified name `Widget` and kind `class` — one for the declaration, one for the
`extension Widget` block. Their ids do not collide: `_dedupe_ids`
(`src/loci/parser/extractor.py:1363`) appends a `~N` suffix, giving
`…::Widget#class` and `…::Widget#class~1`. Scanned across the whole lott-ios
corpus (4,486 files, 36,932 symbols) and loci's own source, there are zero id
collisions, so nothing is being lost today.

The consequence for this plan is different: **there is no single node meaning
"the type `Widget`"**. Member resolution must therefore key a member on its
owning type *declaration byte range*, and treat "which type am I inside" as a
lexical question answered from the enclosing declaration — never as a lookup by
type name or symbol id. The same shape appears for Rust `impl` blocks and for
any language allowing a type to be declared in more than one place.

Task 3's test matrix must include a type declared once and extended once in the
same file, with a member call from each half reaching the right target.

## Incremental Tasks

### Task 1 — Deferred callable visibility — **done** (`b8bac76`)

Built as specified with one correction found on contact: **only Python was
affected.** JavaScript, TypeScript, Go, Rust and Swift already bind a callable
declaration with `active_start_byte=scope.start_byte`, so they hoist already.
Verified with a forward-reference fixture in each of the five.

The rule shipped is narrower than "the owner is a callable". `python_scope`
returns the enclosing *definition node*, not its body, so an owner-body test
would have wrongly admitted a nested `def` called earlier in the very same
body — a real `NameError`. `_visible_to_deferred_call`
(`src/loci/parser/calls.py`) therefore requires the call site's owner
definition to be contained in, and not identical to, the binding's scope.

`EXTRACTOR_VERSION` went 13 to 14: extraction output changes, so existing
indexes must be rebuilt.

### Checkpoint A — re-measured 2026-08-25

| Corpus | definite before | definite after | absent before | absent after |
|---|---:|---:|---:|---:|
| Python (`src/loci`, 9,335 sites) | 374 | 2,171 | 5,312 | 3,516 |
| Swift (lott-ios, 126,406 sites) | 592 | 592 | 60,112 | 60,112 |

**Consequence for the rest of this plan.** Swift gained nothing, so its 17,346
bare-lowercase unresolved calls are *not* forward references — they are member
calls under implicit self, or calls into other files in the same module. That
confirms Task 3 and the Swift module work as the only routes to them, and
removes forward-referencing as a candidate explanation.

Full suite: 1,355 passed, 2 failed. Both failures
(`test_enforce_read_hook::test_nested_indexed_repo_uses_longest_matching_root`,
`test_store_isolation::test_mcp_binding_uses_inherited_suite_store_boundary`)
reproduce identically on the unmodified tree and are unrelated to this work.

### Task 2 — Member candidate collection — **done** (`5fcbcda`)

`SyntaxContext` gains `member_bindings`; `RawCallSite` gains
`member_candidates` and `member_binding_state`. Observation only — no edge
changes and no graph code touched. `EXTRACTOR_VERSION` 14 to 15.

Members are keyed by the body that lexically contains the call, never by type
name, per the constraint recorded above. Swift is the one exception: extension
members pool with their declaration when both sit at file scope, which is safe
because no other supported language lets a second declaration of the same name
extend the first.

Covered shapes: Swift implicit self (bare name inside a type body), Python
`self.` / `cls.`, JavaScript and TypeScript `this.`. Go receivers and Rust
`self` are not covered — Go binds a receiver name rather than a type body, and
Rust `self.x()` is still classified `dynamic`, so both need their own work.
Protocol requirements and other body-less declarations are excluded outright.

Measured yield over the same corpora:

| Corpus | definite local | definite member | ambiguous member |
|---|---:|---:|---:|
| Swift (lott-ios, 126,406 sites) | 592 | 8,240 | 567 |
| Python (`src/loci`, 9,418 sites) | 2,177 | 80 | 0 |

The Python figure is low because loci's own source is mostly module-level
functions, not methods — it is not evidence about Python generally.

Also fixed in passing (`20ea7cf`): the MCP `loci_graph_calls` output model
pinned `language` to the five pre-Swift languages, so it rejected its own
output for any Swift repository. The schema fixture only ever indexed Python,
so nothing caught it. A new test ties the literal to the parser's supported
set.

### Task 3 — Implicit-self and explicit-self member resolution — **done**

Member candidates now become call edges. Covers bare names inside a type body
(Swift implicit self), `self.x()` / `cls.x()` (Python) and `this.x()`
(JavaScript, TypeScript).

**Deviation from this document: no new resolution tier was added.** The spec
said `CallResolution` gains `"member-resolved"`. That is the wrong lever.
`CallRecord.resolution` feeds straight into `GraphEdge.resolution`, which is a
`ResolutionTier` — the graph-wide vocabulary shared by import, reference and
contains edges, filtered on by `SAFE_GRAPH_RESOLUTIONS` in `traversal.py` and
exposed on the neighbours, paths and anchors MCP schemas. A member call is
proven the same way a local call is — lexically, in one file, against an
indexed definition — so it is the same *tier*; what differs is the *route*, and
`resolution_basis` is the field that already carries the route. Member calls
therefore resolve as `resolution="exact"` with
`resolution_basis="member_callable"`, and nothing outside `graph/calls.py`,
`graph/_call_validation.py` and the MCP call schema had to change.

The consumer-visible consequence to keep in mind: `member_callable` edges point
at the lexically visible definition. Where a subclass overrides the member,
runtime dispatch may go elsewhere. Inheritance is out of scope, so that risk is
carried by the basis field rather than by a weaker tier.

Resolution order is local, then member, then imported reference — but any two
surviving targets fail closed as `conflicting_resolution` rather than being
ranked. That is what makes a Swift member colliding with a file-scope function
of the same name unresolved instead of silently member-resolved: proving
Swift's shadowing rule is not in scope.

Two new unresolved reasons, both reported only after the local and reference
branches have failed, so they never displace an existing outcome:
`member_binding_ambiguous` and `member_target_not_indexed`.

`EXTRACTOR_VERSION` 15 to 16. The first version of this note said no bump was
needed because extraction output is unchanged. That was wrong: graph state is
persisted in the index and re-validated against the *current* resolver on every
graph read (`service.py` lines 822, 1382, 1659, 1761, 1894 all call
`store.validate_graph_state`). A graph built by the old resolver against an
index whose version still matched would therefore hard-fail on read rather than
be rebuilt. Verified by handing `validate_call_records` the record the
pre-Task-3 resolver produced for a `self.helper()` site and watching it raise
`Resolved call outcome does not match current local/reference evidence`.

`EXTRACTOR_VERSION` is the wrong name for this gate — it forces a full
re-extraction to invalidate a purely resolver-side change. A separate graph
resolver version belongs in Task 7.

#### Measured after Task 3

| Corpus | resolved before | resolved after | local basis | member basis |
|---|---:|---:|---:|---:|
| Swift (lott-ios, 126,406 sites) | 586 | 8,820 | 586 | 8,234 |
| Python (`src/loci`, 9,437 sites) | 2,183 | 2,263 | 2,183 | 80 |

Swift resolved calls rise 15-fold. The remaining Swift unresolved mass is
92,619 `callee_not_proven` (cross-file module calls and receiver-typed
`obj.method()`) and 21,926 `unsupported_callee` (dynamic callees, which Task 4
reduces). 567 sites are `member_binding_ambiguous` — a real overload or a
same-named member in a pooled extension.

Swift parsing still fails outright on 76 of 4,486 files with `SourceParseError`;
that is pre-existing and unrelated.

Full suite: 1,371 passed, 6 failed — the same six pre-existing failures in
`tests/test_enforce_read_hook.py` and `tests/test_store_isolation.py`.

### Task 4 — Swift `self` paths — **done**

`self.foo()` is now a `static_path` callee with path `("self", "foo")`, so it
reaches the member branch built in Task 3 instead of being discarded as
`dynamic`. Swift joins Python and JavaScript in `_EXPLICIT_SELF_ROOTS`.

**Deviation: `_swift_path` was left alone.** This document said to change it.
That would have altered Stage 10 reference observation too, because
`parser/references.py:402` shares the function — and the two consumers want
opposite answers. For a *reference*, `self` names no declaration, and the
function's own docstring says it refuses to guess a root; for a *callee*,
`self` is a definite receiver the member scope can prove. So `calls.py` gained
`_swift_callee_path`, which handles the `self` case and delegates everything
else. Stage 10 output is unchanged, and a test asserts that the shared builder
still returns `None` for every `self`-rooted navigation.

Only a direct `self.<name>` is recognised. `self.inner.record()` calls through
a property whose type is unknown, so it stays `dynamic`; `super.foo()` (1,268
sites) stays `dynamic` because its target is in a superclass.

`EXTRACTOR_VERSION` 16 to 17 — reclassifying a callee changes extraction
output.

#### Measured after Task 4

| Corpus | resolved before | resolved after | member basis | `unsupported_callee` |
|---|---:|---:|---:|---:|
| Swift (lott-ios, 126,406 sites) | 8,820 | 9,932 | 9,346 | 21,926 → 20,097 |

1,829 `self.` call sites were observed, against a prediction of 2,084; the
difference is the 76 files that fail to parse at all. Of those 1,829: 1,112
definite, 113 ambiguous, 604 absent. The 1,112 is the exact gain in resolved
calls.

The prediction was 1,410 resolvable and the outcome is 1,112. The estimate was
optimistic because it credited any method in the file whose qualified-name
prefix matched the enclosing type, whereas member scope only pools an extension
with its declaration when both sit at file scope. The 604 absent sites call
members declared in another file, inherited, or required by a protocol.

### Checkpoint B — re-measure and decide the order of Tasks 5-8 — decided

Modules first. Recorded 2026-08-25 after Task 4.

Tasks 5 and 6 as originally written assumed same-file yields that do not exist.
The decision at this checkpoint is whether to run them now for 1,173 combined
sites, or to finish Swift module resolution first — `swift-modules` and
`swift-resolve` in `docs/plans/2026-08-24-swift-graph-support.md` — after which
the same two tasks reach the 39,066 and 8,372 sites whose targets are declared
in another file.

Current recommendation: module resolution first. Tasks 5 and 6 are cheap to
build either way, and building them second means building them once against the
resolved-type path rather than twice.

### Task 5 — Type initializer resolution

`Widget(...)` → `Widget.init` (Swift) or `Widget.__init__` (Python), under a
new `type_initializer` basis at the `exact` tier. The basis is a call-local
field, so unlike a tier it adds no graph-wide surface.

Measured same-file payoff: 953 Swift sites, 41 Python sites.

Language gating, verified against the grammars:

- **Swift and Python** — the callee is a plain `identifier` / `simple_identifier`,
  so these are `identifier`-form call sites and need a type-name binding
  channel alongside the member one.
- **JavaScript and TypeScript** — `new Widget()` parses as `new_expression`,
  which is **not** in `_CALL_NODE_TYPES` and is therefore not observed as a
  call site at all today. Supporting it means adding a node type to call
  extraction, not just a resolution rule. That is a larger change than this
  task assumed and should be its own decision.
- **Go and Rust** — no constructor call syntax; nothing to do.

A type with no explicit initializer produces no `init` symbol, so `Widget()`
stays unresolved for 4,177 Swift and 228 Python sites where the type is
declared in the file. That is correct — call edges may only point at
`function` or `method` symbols — and must be asserted by a test rather than
left to chance.

### Task 6 — `Type.member()` static paths

Measured same-file payoff: 220 Swift sites. Depends on the same type-name
binding channel as Task 5, so the two should be built together.

### Task 7 — Persistence and a real resolver version

The `EXTRACTOR_VERSION` bumps in Tasks 1-4 are the blunt instrument. Persisted
graph state is validated against the live resolver on every read, so a resolver
change with no version change turns into a read-time contract error for anyone
holding an index. This task introduces a version that names what it gates and
covers incremental re-index integrity.

### Task 8 — Service, health, MCP diagnostics, documentation

Smaller than it reads. `graph_calls` serialises through `record.to_dict()`, so
new record fields already reach the MCP surface once the output model allows
them — which is why only `mcp_output_models.py` needed touching in Task 3.
What is genuinely missing is a breakdown by `resolution_basis` in
`graph_health`, which today counts only resolved versus unresolved.

## Required Test Matrix

- Forward reference inside a callable body resolves; forward reference at file
  scope does not.
- A member name that collides with a file-scope function is `ambiguous`, not
  silently member-resolved.
- A member call inside a type body does not resolve to a same-named member of a
  *different* type in the same file.
- `self.x()` where `x` is a stored property holding a closure resolves to
  nothing, not to a same-named method. **Not met as of Task 3.** Verified: a
  Python class that assigns `self.helper = fn` in `__init__` *and* defines a
  method `helper` resolves `self.helper()` to the method, which is wrong —
  at runtime the instance attribute wins. Closing it needs a stored-property
  channel that forces `member_binding_state="shadowed"` when an attribute
  assignment in the same type body collides with a member name. Rare enough in
  practice to defer, real enough to record; it belongs with Task 7 or later,
  and the matrix line stays here until it passes.
- A protocol requirement call stays unresolved.
- An `extension` member and a declaration member of the same type both resolve.
- A call to an inherited member stays unresolved.
- `Widget()` resolves to `Widget.init` only when that initializer is indexed.
- Every existing Stage 11 call test still passes unchanged.

## Verification

```
.venv/bin/python3 -m pytest tests/parser tests/graph -q
.venv/bin/python3 -m pytest tests/ -q
```

Plus a re-run of the measured baseline in this document against both corpora,
with the before/after table recorded here on completion.

## Rollback

Each task is a separate commit on `swift-graph-support`. The original claim
that Task 7 held the only irreversible step was wrong — Tasks 1, 2 and 3 each
bumped `EXTRACTOR_VERSION` (13 to 16), and Task 4 will too, because every one
of them changes what a persisted index must contain to validate. Since the
branch is unpushed, revert remains a branch delete plus a re-index.

## Owner Review Decision

Pending.
