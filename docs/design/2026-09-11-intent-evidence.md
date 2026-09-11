# W2.4 — Select useful source for an explicit retrieval intent

Date: 11 September 2026. Canonical Objective:
`obj_0110c8712b21bdd2c12532f189d84a74`. Parent Task:
`task_2d0b577ecf3742cbd07e0b6527f9facf`.

W2.3 made the missing type relationships available. Its deterministic Anvil
check returned 4, 12 and 14 related definitions where the three questions needed
4, 6 and 4. W2.2's earlier measured automatic-expansion policy remains rejected.
W2.4 selects source for a stated purpose and makes the complete result bounded;
it does not perform the later agent comparison or claim measured workflow gains.

## One small interface

Add `loci_explore(repo, intent, query="", seed_ids=None, max_hops=None,
max_output_bytes=16384, max_evidence_bytes=8192, resolutions=None)`.
The existing graph retriever selects two endpoints, searches paths and checks
question wording; its budget covers relationship lines, and it does not return
target definitions. Extending that contract to single-anchor source selection
would combine different caller obligations and response meanings. This small
composition instead reuses anchor selection, proven graph adjacency, persisted
records and cached source hydration. Existing diagnostics remain the exact
control and investigation route.

| Intent | Selection | Meaning and limits |
|---|---|---|
| `locate` | Explicit source symbols or ranked name/query anchors; no traversal. | Find source locations and definitions. |
| `type_dependencies` | Outgoing `uses_type`, `extends`, `implements`. | Immediate declaration contracts, alias/type-query/constraint and heritage continuation; deeper property branches need a query match. |
| `impact` | Incoming calls, references and type/heritage edges. | Known static dependents; default one hop. This does not establish complete impact, dynamic dispatch or affected-test coverage. |

The caller chooses the intent; question wording does not silently select a
different relation meaning. An unsupported intent returns a structured input
error identifying the supported intents and `locate` fallback. Execution-path,
test-selection and value-origin plans are outside this first interface.

Default resolutions are `exact` and `import-resolved`. The caller can narrow
that list, including an empty list. Candidate, heuristic and custom declared
edges do not enter this workflow; inspect them through diagnostic graph tools.
Every returned relation retains the stored edge and actual traversal direction.

## Selection relevance

For a function whose parameter is `Order`, return `Order` first. If the
question concerns its `customer` field, follow that proven field dependency to
`Customer`; leave an unrelated `audit` branch out. An alias chain remains useful
without repeating every alias name in the question. Asking for known dependents
of `Order` instead walks incoming links and preserves each stored direction.

Anchor selection reuses the existing scorer. Explicit seeds keep their order;
inferred anchors exclude zero-width graph file/package/crate nodes. The source
workflow reports unsupported explicit anchors rather than treating a file node
as a declaration. Locate also supports positive-span Markdown source.

Type selection tokenizes camelCase and snake_case identifiers and removes exact
anchor-name mentions and generic question words. It compares remaining terms to
the target name and the authored property's local label. These are relevance
hints, not target-resolution proof or a claim that selected source is necessary.
Direct contracts and structural alias/heritage continuation have higher priority
than topical property branches. Edge-kind weights, decreasing path priority and
existing graph hub thresholds keep ordering deterministic and penalize hubs.
Impact follows only the stored static relation subset and shows that scope.

The walk examines at most 64 nodes and 32 neighbors per expansion, admits at most
12 source items and uses at most three inferred or five explicit anchors. Type
walks default to three hops, impact to one and locate to zero; an explicit hop
limit is between zero and four. Cycles, alternative paths, low-relevance branches,
unresolved records and work-limit omissions are distinct. Only one selected
proof path per source item is needed for the compact result.

## Source and complete response budget

The result has small `items`, `relationships` and shared `sources` arrays.
Each item identifies its role, source, depth, reason and relationship path.
Each relationship retains its original graph edge, traversal direction and
supporting source IDs. Source entries have exact UTF-8 intervals, line bounds,
full-file hashes and content. Cached definition hashes and record support hashes
must validate before delivery; stale or missing source omits the affected bundle.

The packet owns no stored semantic records. It selects from the validated graph
and separately hydrates definition and authored/import/re-export evidence.
Existing cached-source readers are reused. Exact and already-contained spans
share source entries; evidence accounting uses the union of delivered byte
intervals within each file/hash version. Missing ancestors cannot leave a
plausible-looking detached path in the output.

Packing follows selection priority. A related definition and its missing proof
source fit atomically or are skipped so a smaller later item can still fit.
Oversized anchors may return an explicit UTF-8-safe prefix, preferably ending on
a line boundary; the item is marked incomplete and reports `source_clipped`.
Related definitions and required proof lines are never silently abbreviated.

`max_output_bytes` covers the entire canonical UTF-8 JSON MCP tool result:
`content`, `structuredContent` and `isError`, including selection metadata,
source, relationship explanations, counts and omissions. It excludes the
JSON-RPC request ID/transport envelope. Self-reported output size and estimated
tokens are included in the fixed-point size calculation. The estimate is
`ceil(output_bytes / 4)`, labelled `utf8_bytes_div_4`; it is not tokenizer usage.
Evidence and complete-output limits are enforced independently.

Output limits accept 2,048–262,144 bytes; evidence limits accept 0–65,536 bytes.
The query is at most 4,096 UTF-8 bytes. Input errors and absent anchors are
explicit. Source coverage remains `complete`, `partial` or `unknown` as recorded
by the index; relationship scope is always non-exhaustive. `ok` means the chosen
packet was delivered, not that the repository question is fully answered.
`partial` exposes source/uncertainty/budget omissions; `empty` has no source items.

## Acceptance and delivery

The four leaf Tasks cover intent plans (W2.4.1), grounded source selection
(W2.4.2.1), complete packing (W2.4.2.2) and usable MCP workflow (W2.4.3).
Acceptance exercises source ownership, real freshness, exact and ambiguous
bindings, direction, hub/cycle bounds, non-ASCII spans and JSON sizes, clipped
anchors, atomic related evidence, missing source and exhausted budgets.

Use unchanged frozen source cases as independent positive/negative controls;
keep all gold inputs and expected answers out of normal agent tools. A separate
deterministic Anvil check can compare delivered definitions with W2.3 while
retaining every miss and extra item. One isolated host-mediated MCP exercise
must actually discover and call the new tool against a frozen fixture. Update
the tracked agent guidance with intents, limits and diagnostic escape hatches.
No global runtime promotion or W2.5 agent comparison is part of this stage.
