# W4.3 — JavaScript dependency and class context

Task: `task_b280004a5bac7e5e92970ea053b51bf8`.

`loci_explore(intent="dependencies")` now returns related source for plain
JavaScript. For example, a request starting at `run` returns its imported
`make` and `add` helpers, plus the import/export statements proving their
origins. A request for the known callers of `add` includes `run`, `make` and
`Worker.work`. Starting at `Worker` supplies the class named by its direct base.

This implementation remains on `feat/evidence-backed-exploration`. The shared
runtime is unchanged. Acceptance uses the frozen
[W4.1 source cases](../design/2026-09-12-multilingual-context-cases.md).

## Intent and supported meaning

The new `dependencies` intent follows outgoing definite calls, declaration-owned
imported value references and authored direct class bases in JavaScript. It uses
the existing type-dependency selection for Python and TypeScript. Language
filtering happens before neighbor limits, so unrelated call edges cannot consume
those languages' type-context allowance. The existing JavaScript
`type_dependencies` request retains its explicit unsupported-language outcome.

Direct JavaScript `extends` observations use the shared type family, but require
`language="javascript"`, `relation="extends"`, `context="heritage"` and value
lookup. Exact local classes and contained named/default/namespace import and
re-export routes can prove the base. The relationship records authored syntax;
it establishes no structural type, `implements` relationship or runtime dispatch.
JSDoc is unsupported and creates no type-use records.

Named arrow bodies retain the exact indexed variable-declarator owner. A local
`const` arrow is a definite callee after its initializer, with its own deferred
body also supported. Calls before initialization, mutable callable variables,
anonymous callbacks and single-parameter shadowing stay outside that proof.
Existing declaration-owned imported value references need no new projection.

Visible assignment, update and deletion of a JavaScript target root conservatively
block definite-call and direct-base proof in that file. Mutated exported names
retain their export observations but lose definitive declaration support, so
importers and re-export consumers cannot claim the old function or class target.
This uses the existing ambiguous-export diagnostic. It is deliberately
conservative across scopes and source order; it does not simulate mutation,
resolve aliases or execute repository code. Prototype edits do not create
inheritance edges, and computed calls, dynamic imports, `require` results and
unproven receiver dispatch remain unresolved.

## Frozen source cases

| Case | Delivered and checked |
| --- | --- |
| `javascript_value_dependencies` | Exact `run`, `make`, `add`, arrow/default-identifier exports and barrel proof; the local `make -> add` call is resolved. |
| `javascript_direct_class_base` | Exact `Worker -> Base` authored base, original spelling and complete import/re-export proof. Method-body calls keep their method owner. |
| `javascript_known_call_impact` | `run`, `make` and `Worker.work` reach `add` through incoming traversal while stored call direction remains caller-to-callee. |
| `javascript_unproven_dependencies` | Ambiguous stars, missing default exports, external, shadowed, computed, dynamic and JSDoc cases create no fabricated target. |

The shared packet retains exact declaration bytes, hashes, relationship direction,
source evidence and one complete proof path per delivered definition. Alternative
paths and missing context remain explicit omissions. The frozen 8 KiB source and
16 KiB complete-result budgets are unchanged; reduced and zero evidence checks
retain truthful missing-context outcomes.

## Validation

Focused checks cover the four frozen cases, ordinary imported constants, local
and namespace class bases, lexical and mutation negatives, resolver-control
refresh, source/target/barrel refresh, source hashes and complete packet closure.
The actual stdio MCP check validates the new intent, JavaScript heritage
diagnostics, strict schemas and exact complete-result byte accounting.

The final focused run passes **151 tests**, including 16 JavaScript delivery
and stdio checks:

```sh
.venv/bin/python -m pytest -q \
  tests/test_javascript_context_delivery.py tests/test_javascript_context_mcp.py \
  tests/parser/test_calls.py tests/graph/test_calls.py
```

Existing call/reference extraction and resolution, type records, exploration,
Python delivery and public output-schema checks pass. Extractor version 27
invalidates prior extraction caches. No graph schema or existing record field
changes are required.

The immutable corpus remains 19 cases and 16 snapshots. This milestone measures
source delivery; provider task outcomes and final measurement freezing remain
W4.7 work.

Next: W4.4 Go, `task_5eb1f78e6e2a876259dd9bf3b170288d`.
