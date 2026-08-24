# Plan: Member-Scope Call Resolution

**Status:** proposed — not authorized for implementation

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

This document authorizes no production-code change. Its commit may update only
this plan. Vik must explicitly approve implementation.

Work proceeds on its own branch off `master`, task by task, tests first. The
Swift branch `swift-graph-support` stays unpushed and unmerged until this lands
underneath it; Swift is then finished on top and the whole language ships as one
coherent unit.

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

| Bucket | Sites | Share |
|---|---:|---:|
| bare `Uppercase(...)` — initializer calls | 42,766 | 42.2% |
| static path, non-type head (`obj.method()`) | 32,533 | 32.1% |
| bare `lowercase(...)` — module or member calls | 17,346 | 17.1% |
| static path, `Type.member()` | 8,777 | 8.7% |

`self.foo()` does not appear as a static path because `_swift_path` returns
`None` for a `self` target, so those sites are classified `dynamic` today.

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

`Widget(...)` is 42.2% of Swift's unresolvable sites. The callee is a type
name, and the target is that type's initializer. Symbols already carry what is
needed — `parse_file` on `tests/fixtures/sample.swift` yields
`Widget.init`, `Widget.describe`, `Widget.run` as `method` symbols with
`Type.member` qualified names — but nothing joins a bare `Widget` callee to
`Widget.init`.

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

- `LexicalBinding` gains `deferred_visible: bool`, set for callable
  declarations, meaning "visible to `callable`-owned sites regardless of
  `active_start_byte`".
- New member-scope collection per language, keyed by owning type declaration
  rather than by lexical scope.

### `src/loci/parser/calls.py`

- `_local_call_binding` honours `deferred_visible` when the call site's
  `ExecutableOwner.kind == "callable"`.
- New `_member_call_binding` producing `member_candidates`.
- Swift `_swift_path` returns a path for `self`-rooted navigation instead of
  `None`.

### `src/loci/graph/calls.py`

- `CallResolution` gains `"member-resolved"`; `CallResolutionBasis` gains
  `"member_callable"` and `"type_initializer"`.
- `_resolve_call` gains a member branch, ordered after `_local_target` and
  before the imported-reference branch, and must fail closed with
  `conflicting_resolution` when both a local and a member target survive.
- `_validate_outcome` gains a member arm mirroring the `exact` arm's evidence
  requirements: the target must be an indexed callable, and the support must
  carry the member definition site.
- New unresolved reasons: `member_target_not_indexed`,
  `member_binding_ambiguous`.

## Known Complication — duplicate type symbols

`parse_file` on `tests/fixtures/sample.swift` emits **two** symbols with
qualified name `Widget` and kind `class` — one for the declaration, one for the
`extension Widget` block. `make_symbol_id` is
`f"{file_path}::{qualified_name}#{kind}"`, so both take the same id. Member
resolution keyed on the owning type must therefore key on the type's
*declaration byte range*, not its id, and the id collision itself should be
investigated before this work starts — it may already be corrupting the symbol
index for Swift, C#-style partial types, and Rust `impl` blocks.

## Incremental Tasks

### Task 1 — Deferred callable visibility

Add `deferred_visible` to `LexicalBinding`, set it for callable declarations in
all six collectors, honour it in `_local_call_binding` only when the call
site's owner is `callable`. No new resolution tier — these sites simply become
`definite` and flow through the existing `exact` path.

*Acceptance:* the `early`/`late` fixture above yields `definite` for both; a
module-level forward call (`late()` at file scope, before the declaration)
stays `absent`; `_error` sites in `src/loci/graph/calls.py` resolve.

### Checkpoint A — re-measure

Re-run the baseline tally on both corpora. Record the delta. If Task 1 alone
does not move the Swift bare-lowercase bucket materially, that says the Swift
17,346 are module-level rather than same-file, and Task 3's sizing needs
revisiting before it is built.

### Task 2 — Member candidate collection

Collect members per type declaration in `_binding_context`, emit
`member_candidates` / `member_binding_state` from `calls.py`. Parser only — no
graph change, no new edges.

### Task 3 — Implicit-self and explicit-self member resolution

Add the graph-side member branch, the `member-resolved` resolution and the
`member_callable` basis. Covers bare names inside a type body and `self.x()` /
`this.x()`.

### Task 4 — Swift `self` paths

Stop discarding `self`-rooted navigation as dynamic.

### Task 5 — Type initializer resolution

`Widget(...)` → `Widget.init`, under `type_initializer` basis. Language-gated:
Swift and Python yes, Go no, Rust no, JS/TS only via `new`.

### Checkpoint B — resolver review

### Task 6 — `Type.member()` static paths

### Task 7 — Persistence, `EXTRACTOR_VERSION` bump, incremental integrity

### Task 8 — Service, health, MCP diagnostics, documentation

## Required Test Matrix

- Forward reference inside a callable body resolves; forward reference at file
  scope does not.
- A member name that collides with a file-scope function is `ambiguous`, not
  silently member-resolved.
- A member call inside a type body does not resolve to a same-named member of a
  *different* type in the same file.
- `self.x()` where `x` is a stored property holding a closure resolves to
  nothing, not to a same-named method.
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

Each task is a separate commit on a branch off `master`. The
`EXTRACTOR_VERSION` bump in Task 7 is the only irreversible step for existing
indexes; before it, revert is a branch delete.

## Owner Review Decision

Pending.
