# W5.3 future evaluator and tool contracts

Task `task_63efbc92c3ec5ae63f25361a667950e3` repairs the deterministic defects
identified by the retained multilingual measurement. The repair uses new
`*_v2` modules on the isolated exploration branch. Legacy evaluator modules,
frozen corpora, prompts, engine/harness bundles and all 114 results retain their
original contents and verdicts.

## Boundaries and entry points

- `benchmarks.multilingual_context_observed_v2` owns future trace replay,
  reconciliation and measurement under `multilingual-context-workflow-v2`.
- `benchmarks.multilingual_context_tools_v2` owns the future adapter, schema,
  normalization and explicit stdio entry point.
- `benchmarks.multilingual_context_answers_v2` owns the authored answer schemas,
  model-visible prompt suffix and exact answer checks.

These are deterministic future-use components, not a new provider comparison.
The acceptance fixtures reuse the old source snapshots and established budget
values in temporary repositories with isolated stores. Running a later provider
comparison requires a separately versioned pre-outcome freeze binding the new
prompt, tool surface, evaluator, source engine, controls and schedule. The old
comparison runner and freeze are not silently redirected to the new modules.

## Graph delivery accounting

The retained defect conflated the public operation name in the delivery ledger
(`graph_imports`, for example) with the internal source-trace name (`graph`).
The future reconciler distinguishes those identities while matching normalized
arguments, exact delivered JSON and byte counts, source spans and unique trace
IDs. A name mapping does not waive any other evidence check.

Invalid, duplicate, mismatched or missing records cannot provide complete
accounting or validated source evidence. A matched source-free tool rejection
can still have known output cost and zero source bytes; it supplies no successful
source or relationship proof. A later successful request can recover from such
an error without pretending that the error itself delivered evidence.

## Tool bounds

Record tools publish and enforce offset 0–10,000 and limit 0–32. Explicit graph
seed/source/target arrays publish and enforce the inherited maximum of five.
The future normalizer and dispatch use the same bounds. Existing null, duplicate
and empty-list meanings are retained where the underlying tool supports them.
Both arms retain the same exact-read tools; B adds `loci_explore`.

The W5.1 route makes tracked `go.mod` and `Cargo.toml` source equally accessible
to both arms. The repair preserves exact source, retrieval accounting and the
existing independent evidence/output budgets.

## Exact answers

All 19 case IDs have authored JSON schemas. Their representation rules state
which fields are declaration-file paths, `file::Qualified.name` endpoints,
strings, ordered pairs, sorted arrays, field-name/type maps, booleans or numbers.
Declaration files use repository-relative POSIX paths without a leading `./`,
an import specifier, symbol suffix or kind suffix. Endpoint fields add the
qualified declaration name and omit Loci's `#kind` suffix.

The same answer contract is appended for both arms. Schemas are authored from
task semantics, not inferred from gold answers; no expected values, required
source spans or evaluator relationship labels are added to the prompt. Source
spelling and certainty still matter. A schema-valid answer can be factually
wrong, so scoring also retains the existing strict JSON-fact comparison.
Object order is irrelevant; ordered pairs and exact array/string values remain
significant. JSON numbers compare by value and booleans remain distinct.

## Acceptance

The directly relevant acceptance command passed **99 tests**:

```sh
.venv/bin/python -m pytest \
  tests/test_multilingual_context_answers_v2.py \
  tests/test_multilingual_context_observed_v2.py \
  tests/test_multilingual_context_tools_v2.py \
  tests/test_multilingual_context_observed.py \
  tests/test_multilingual_context_tools.py \
  tests/test_multilingual_context_compare.py -q
```

- An actual subprocess runs the v2 stdio entry point and invokes all eight
  advertised graph routes. Delivered arguments, bytes, spans and trace IDs
  reconcile exactly, including a source-bearing call path. Corrupted copies of
  the live operation, byte, span and trace records fail accounting.
- Deterministic integrity negatives cover missing/duplicate attempt and trace
  IDs, wrong protocol/schema, mismatched metadata and arguments, and fake
  successful deliveries without source-trace records. A truthful source-free
  rejection retains cost while contributing no validated proof.
- The stdio preflight constructs the real adapter for A/B against frozen Go and
  Rust snapshots. It reads exact control files, accepts offset 10,000/limit 32
  and five real seed IDs, and rejects limit 33 and six IDs. In-process checks
  cover the remaining zero, negative, over-limit and nullable boundaries across
  schema, normalization and dispatch.
- Answer checks cover all 19 expected shapes, mutations of every answer field,
  false certainty, ordering, paths/endpoints and prompt independence from
  evaluator-only facts. Measurement uses the explicit answer check and still
  refuses a full pass when source/relationship proof is absent.

`git diff --check` passed. The comparison against W5.2 base `2f676a6` confirms no
changes to source engine, frozen corpora, comparison bundles, results or legacy
evaluator/tool/prompt modules. No historical result was rescored. These checks
establish deterministic contracts; they do not measure workflow efficiency.

## Next work

After W5.3, the next task is W5.4 source integration,
`task_ac21c3c2d3153e5a4e28879935240777`. It retains its explicit release-direction
gate. Installed-runtime promotion is the separate W5.5 task. Canonical Manifest
authority remains `/Users/brummerv/loci`; this source work stays in
`/Users/brummerv/phluxxed/loci-exploration` until integration is directed.
