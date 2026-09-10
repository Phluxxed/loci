# TypeScript generic-shadow repair (W2.1.4)

The frozen W2.1.1 `generic_shadow` fixture previously produced three resolved
references and one false `references_type` edge from a local generic parameter
to `types.ts::Payload#interface`. Its strict TypeScript language control already
proved that the local generic was independent of the imported interface.

The repair adds lexical type-parameter bindings for the grammar's
`type_parameters` lists. Their scope is the containing declaration or signature,
including its constraints and defaults. Only parameter declaration names are
excluded from reference extraction. Uses matching an import remain observable
as `shadowed` raw references and `binding_shadowed` unresolved records with no
proven target or reference edge.

Type parameters occupy the type namespace. Same-named value references, calls
and `typeof` queries remain eligible for normal import resolution. Other imported
types used in constraints or defaults, and same-named imports outside the generic
scope, retain their evidence. Executable-owner rules are unchanged.

The supported syntax boundary is a TypeScript/TSX `type_parameters` list with
named `type_parameter` children: function declarations and expressions, arrows,
classes, interfaces, aliases, methods, callable signatures, and function and
constructor types. Mapped-type binders and conditional `infer` binders use
different syntax and are outside this repair; this is not a claim of complete
TypeScript type-scope resolution. Local generic bindings do not become graph
symbols or local type-dependency edges. Extractor version 24 rebuilds old caches.

## Exact original reproduction

Run in the isolated development worktree:

```sh
.venv/bin/python tests/reproductions/typescript_context_gaps.py --output /tmp/loci-w214-postfix.json
```

The declaration-name observation at byte 72 is absent. The two uses at bytes
88–95 and 98–105 are `shadowed`, unresolved with `binding_shadowed`, no target,
and no support. Only the authored file import edge remains; no `references_type`
edge exists. The arrow and default-identifier repairs still resolve their correct
endpoints, and the other original fixture counts are unchanged. The original
[baseline report](./2026-09-10-typescript-context-gaps.md) and frozen JSON packet
remain unchanged, retaining the adversarial case for corpus work.

## Acceptance checks

```sh
.venv/bin/python -m pytest tests/test_typescript_generic_shadow.py -q
.venv/bin/python -m pytest tests/parser/test_references.py tests/parser/test_calls.py tests/graph/test_references.py -k 'javascript or typescript' -q
.venv/bin/python -m pytest tests/storage/test_index_store.py::test_index_versions_rejects_old_extractor_version tests/test_service.py::test_service_old_extractor_cache_forces_full_reindex -q
```

All 54 focused checks passed: 32 dedicated regressions, 20 existing language
checks, and two cache refresh checks. `git diff --check` also passed.

The regression file checks raw names and spans, resolved records, graph edges,
scope boundaries and positive imported targets. Code remains on the isolated
`feat/evidence-backed-exploration` branch; shared Manifest state belongs to the
original `/Users/brummerv/loci` repository.
