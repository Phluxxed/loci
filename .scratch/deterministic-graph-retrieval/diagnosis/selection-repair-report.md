# W1.8.4.2 selection repair receipt

## Implemented change

`retrieve_context` now packs selected anchors and their native owner identity as
before, then gives those anchors one direct semantic traversal stage before
ownership-lifted files and representative members expand. An edge connecting
two explicit anchors is moved ahead of the ordinary queues in that stage. The
remaining steps use the same extracted `_traverse_relationships` scheduler as
the anchor stage, preserving the existing per-anchor family/direction queues,
neighbor ranking, traversal accounting, node checks, proof hydration, atomic
`Addition`, and follow-on depth behavior.

After the anchor stage, the original ownership expansion still runs. Exact file
anchors therefore still select representative members; symbol anchors retain
their definition, native file node, and `indexed_file` ownership association.
No graph family, proof source, control, public argument, limit, schema, packer,
or locator changed.

Changed product/test files:

- `src/loci/retrieval.py`
- `tests/test_retrieval.py`

New repair receipts:

- `selection-repair-red.json`
- `selection-repair-tests.json`
- `selection-repair-replay.py`
- `selection-repair-replay.json`
- this report

## Pressure regression

The new compact TypeScript fixture contains a consumer options type, a public
type barrel, the defining binding type, resolver controls, and six unrelated
same-file declarations. Before the product change, its focused test failed with
`StopIteration`: neither result exposed the required relation. The exact red
command and failure are retained in `selection-repair-red.json`.

After the change, both the `CaptureCommandResultOptions` query and the explicit
`[CaptureCommandResultOptions, WorkContextBinding]` seed pair return:

```text
service.ts::CaptureCommandResultOptions#type
  -- uses_type / import-resolved -->
binding.ts::WorkContextBinding#type
```

Each relationship has `proof=complete` and response-local proof sources from
`service.ts`, `public.ts`, `binding.ts`, `package.json`, and `tsconfig.json`.
The test also asserts both native file ownership associations and the fixed
evidence/output limits. A separate exact-program-file test proves that the
first three representative members remain selected.
Another high-fanout regression puts an explicit-anchor call beyond the ordinary
32-neighbor cut and verifies that explicit-pair priority happens before that
cut, while `neighbor_limit` remains reported.

## Fixed Anvil replay

`selection-repair-replay.py` created a fresh store under `/tmp`, indexed the
fixed t23 source, ran every request twice, asserted exact repeated equality,
and removed the store afterward. The before/after source manifests are equal:
638 files, 16,142,241 bytes, manifest SHA256
`d450584ade987a84734b631d5740428d7a50c950328ff45f5655051a0289b197`.

All requests used the unchanged normal limits:

| Limit | Value | Limit | Value |
| --- | ---: | --- | ---: |
| `max_hops` | 2 | `max_nodes` | 64 |
| `max_neighbors` | 32 | `max_items` | 12 |
| `max_anchors` | 3 | `max_explicit_anchors` | 5 |
| `max_owner_members` | 3 | `max_evidence_bytes` | 8,192 |
| `max_output_bytes` | 16,384 | `max_anchor_source_bytes` | 1,024 |
| `max_related_source_bytes` | 768 | `max_lookup_bytes` | 33,554,432 |
| `max_lookup_files` | 4,096 | `max_literal_matches` | 256 |

Replay results:

| Request | Required proof | Output / evidence B | Relationships | Omissions |
| --- | --- | ---: | ---: | --- |
| `CaptureCommandResultOptions` | delivered, IDs `[1,7,8,9,10,11]` | 16,091 / 2,787 | 4 | `neighbor_limit=4`, `cycle=3`, `alternative_path=1`, `unresolved_relation=68`, `ambiguous_relation=5`, `external_relation=15`, `source_preview=1`, `output_budget=80` |
| `WorkContextBinding` | particular consumer omitted | 16,267 / 2,723 | 5 | `node_limit=8`, `neighbor_limit=4`, `cycle=4`, `alternative_path=3`, `unresolved_relation=120`, `ambiguous_relation=50`, `external_relation=10`, `output_budget=81` |
| explicit pair, `binding contract` | delivered, IDs `[1,3,4,5,6,7]` | 16,019 / 2,787 | 4 | `neighbor_limit=4`, `cycle=3`, `alternative_path=2`, `unresolved_relation=68`, `ambiguous_relation=5`, `external_relation=15`, `source_preview=1`, `output_budget=79` |
| `runBrowserCli` | both call controls delivered | 14,417 / 3,729 | 3 | `node_limit=20`, `cycle=5`, `alternative_path=1`, `unresolved_relation=46`, `ambiguous_relation=3`, `external_relation=11`, `source_preview=2`, `output_budget=71` |
| `renderActiveTask` | both call controls delivered | 16,117 / 2,808 | 6 | `cycle=5`, `alternative_path=2`, `unresolved_relation=141`, `ambiguous_relation=5`, `external_relation=1`, `source_preview=1`, `output_budget=64` |

Proof IDs are local to each response. The capture and explicit-pair binding
relationships both retain the exact stored edge evidence at
`src/tool-results/service.ts:56`, the line-23 import, line-23-to-30 public
barrel, line-28 definition, and both resolver controls. Their proof source IDs
map exactly as follows:

| Response | Source IDs and files |
| --- | --- |
| capture | `1 service.ts:53-60`; `7 service.ts:23`; `8 work-context/index.ts:23-30`; `9 work-context/binding.ts:28`; `10 package.json:1-30`; `11 tsconfig.json:1-15` |
| explicit pair | `1 service.ts:53-60`; `3 service.ts:23`; `4 work-context/index.ts:23-30`; `5 work-context/binding.ts:28`; `6 package.json:1-30`; `7 tsconfig.json:1-15` |

The broad `WorkContextBinding` query remains bounded and does not select the
particular capture-options consumer. This is expected: the diagnosis found 36
direct neighbors and ranked that consumer at zero-based position 17. The
repair addresses proof displaced by incidental ownership context; it does not
turn a broad impact query into a guarantee for one caller.

## Browser and renderer controls

The browser request retains both required directions:

- forward exact `runBrowserCli -> browserCliUsage`, proof IDs `[1,2]`;
- reverse import-resolved `bin/anvil.ts::main -> runBrowserCli`, proof IDs
  `[4,5,6,7,8,9,10]`, including `src/browser/index.ts:57` as ID 7 and both
  resolver controls.

The renderer request retains:

- forward exact `renderActiveTask -> truncateText`, proof IDs `[1,2]`;
- reverse exact `renderContinuityFrame -> renderActiveTask`, proof IDs `[3,1]`.

These checks use the fixed source and local deterministic retrieval only. No
actual-host activation, model/provider work, or new adoption trial occurred.

## Verification

- `tests/test_retrieval.py`: 16 passed in 0.58 seconds.
- `tests/test_normal_mcp.py tests/test_mcp_server.py`: 47 passed in 38.21
  seconds after the final priority-before-cut adjustment.
- `git diff --check -- src/loci/retrieval.py tests/test_retrieval.py`: passed.
- Five fixed-source requests repeated exactly; every delivered relationship
  has complete proof and every response remains under both byte limits.

The full replay, including every selected relationship, exact hashes, proof
source extents, limits, usage and omissions, is in
`selection-repair-replay.json`.
