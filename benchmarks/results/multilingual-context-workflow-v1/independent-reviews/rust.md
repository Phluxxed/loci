# W4.7 frozen Rust slice audit

Scope: the 24 retained `rust_*` attempts in `/Users/brummerv/phluxxed/loci-exploration/benchmarks/results/multilingual-context-workflow-v1`, checked against the byte-identical frozen corpus at `benchmarks/comparisons/multilingual-context-workflow-v1/inputs/corpus.json` and protocol/controls at `benchmarks/comparisons/multilingual-context-workflow-v1/{protocol.md,inputs/comparison-controls.json}`. This review preserves every frozen score and does not calculate replacement null metrics, rescore, retry, or make an efficiency claim.

## Frozen counts

`Ans`, `Task`, `Full`, and `Meas` are counts of the corresponding frozen booleans. `Src` is the sum of unique required intervals delivered, followed by the number of attempts with all required intervals. `Rel` is the sum of required semantic meanings delivered, followed by the number of attempts with all required meanings.

| Case | Arm | Ans | Task | Full | Meas | Src | Src complete | Rel | Rel complete | Frozen outcomes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `rust_authored_trait_contract` | A | 0/3 | 0/3 | 0/3 | 3/3 | 24/27 | 0/3 | 0/33 | 0/3 | 3 completed |
|  | B | 1/3 | 1/3 | 0/3 | 3/3 | 27/27 | 3/3 | 17/33 | 0/3 | 3 completed |
| `rust_contained_optional_reexport` | A | 0/3 | 0/3 | 0/3 | 0/3 | 15/24 | 0/3 | 0/6 | 0/3 | 3 tool failure |
|  | B | 0/3 | 0/3 | 0/3 | 2/3 | 24/24 | 3/3 | 6/6 | 3/3 | 2 completed, 1 tool failure |
| `rust_known_call_impact` | A | 3/3 | 1/3 | 0/3 | 1/3 | 14/18 | 0/3 | 0/9 | 0/3 | 1 completed, 2 tool failure |
|  | B | 3/3 | 3/3 | 0/3 | 3/3 | 16/18 | 2/3 | 2/9 | 0/3 | 3 completed |
| `rust_unproven_contracts` | A | 0/3 | 0/3 | 0/3 | 0/3 | 18/21 | 0/3 | 0/3 | 0/3 | 2 budget exhausted, 1 tool failure |
|  | B | 0/3 | 0/3 | 0/3 | 0/3 | 21/21 | 3/3 | 3/3 | 3/3 | 3 budget exhausted |
| **Rust total** | **A** | **3/12** | **1/12** | **0/12** | **4/12** | **71/90** | **0/12** | **0/51** | **0/12** | 4 completed, 6 tool failure, 2 budget exhausted |
| **Rust total** | **B** | **4/12** | **4/12** | **0/12** | **8/12** | **88/90** | **11/12** | **28/51** | **6/12** | 8 completed, 1 tool failure, 3 budget exhausted |

The aggregate source denominator is 90 per arm and the relation denominator is 51 per arm. Every one of the 24 frozen `full_pass` fields is false.

## Every retained row

`A/T/F/M` gives answer/task/full-pass/measurement-complete as `1` or `0`. Counts are the frozen source and relationship fields. “Graph name” is the already documented ledger/internal-operation mismatch; “unmatched” is its downstream unmatched-ledger record.

| Attempt | A/T/F/M | Source | Relations | Outcome | Retained failure evidence |
| --- | --- | ---: | ---: | --- | --- |
| `rust_authored_trait_contract-r1-A` | 0/0/0/1 | 8/9 | 0/11 | completed | none |
| `rust_authored_trait_contract-r1-B` | 0/0/0/1 | 9/9 | 9/11 | completed | none |
| `rust_authored_trait_contract-r2-A` | 0/0/0/1 | 8/9 | 0/11 | completed | none |
| `rust_authored_trait_contract-r2-B` | 1/1/0/1 | 9/9 | 3/11 | completed | none |
| `rust_authored_trait_contract-r3-A` | 0/0/0/1 | 8/9 | 0/11 | completed | none |
| `rust_authored_trait_contract-r3-B` | 0/0/0/1 | 9/9 | 5/11 | completed | invalid `get` lineage, retained and counted |
| `rust_contained_optional_reexport-r1-A` | 0/0/0/0 | 5/8 | 0/2 | tool failure | graph name x9 + unmatched; two Cargo cache errors; two pagination errors |
| `rust_contained_optional_reexport-r1-B` | 0/0/0/1 | 8/8 | 2/2 | completed | none |
| `rust_contained_optional_reexport-r2-A` | 0/0/0/0 | 5/8 | 0/2 | tool failure | graph name x5 + unmatched; invalid `get` lineage; Cargo cache error |
| `rust_contained_optional_reexport-r2-B` | 0/0/0/0 | 8/8 | 2/2 | tool failure | graph name x3 + unmatched; Cargo cache error |
| `rust_contained_optional_reexport-r3-A` | 0/0/0/0 | 5/8 | 0/2 | tool failure | graph name x4 + unmatched; two Cargo cache errors |
| `rust_contained_optional_reexport-r3-B` | 0/0/0/1 | 8/8 | 2/2 | completed | none |
| `rust_known_call_impact-r1-A` | 1/0/0/0 | 5/6 | 0/3 | tool failure | graph name x5 + unmatched; Cargo cache error |
| `rust_known_call_impact-r1-B` | 1/1/0/1 | 4/6 | 0/3 | completed | none |
| `rust_known_call_impact-r2-A` | 1/1/0/1 | 5/6 | 0/3 | completed | none |
| `rust_known_call_impact-r2-B` | 1/1/0/1 | 6/6 | 1/3 | completed | none |
| `rust_known_call_impact-r3-A` | 1/0/0/0 | 4/6 | 0/3 | tool failure | graph name x2 + unmatched |
| `rust_known_call_impact-r3-B` | 1/1/0/1 | 6/6 | 1/3 | completed | none |
| `rust_unproven_contracts-r1-A` | 0/0/0/0 | 6/7 | 0/1 | budget exhausted | graph name x10 + unmatched; hidden five-seed bound; pagination; input 201,247 > 200,000 |
| `rust_unproven_contracts-r1-B` | 0/0/0/0 | 7/7 | 1/1 | budget exhausted | graph name x5 + unmatched; pagination; input 239,741 > 200,000 |
| `rust_unproven_contracts-r2-A` | 0/0/0/0 | 6/7 | 0/1 | budget exhausted | graph name x10 + unmatched; Cargo cache error; two pagination errors; input 201,099 > 200,000 |
| `rust_unproven_contracts-r2-B` | 0/0/0/0 | 7/7 | 1/1 | budget exhausted | graph name x6 + unmatched; two pagination errors; input 238,272 > 200,000 |
| `rust_unproven_contracts-r3-A` | 0/0/0/0 | 6/7 | 0/1 | tool failure | graph name x4 + unmatched; Cargo cache error |
| `rust_unproven_contracts-r3-B` | 0/0/0/0 | 7/7 | 1/1 | budget exhausted | graph name x6 + unmatched; unsupported explore resolution request, two pagination errors, Cargo cache error; input 240,096 > 200,000 |

The row values come directly from each attempt's `result.json`. The raw tool requests/responses and ledger are beside it in `events.json` and `adapter-trace.json`.

## Answer findings and prompt-visible contract

The corpus-level `answer_contract` says `exact_json_facts_v1`, but also says answers and labels are evaluator-only. The frozen protocol keeps gold and scorer code away from the task agent (`protocol.md:31-37`). The common prompt requests only the requested JSON, while each ordinary Rust prompt names fields without providing the gold object's exact scalar/endpoint spelling. Exact frozen answer failures remain real score failures, but several do not demonstrate a source-comprehension error.

- **Authored trait contract:** all six answers give the right `u64`, Render/Format facts, implemented traits, and `dynamic_call_target_proven: false`. Five fail exact equality through natural richer encodings: `T: Render` instead of `Render`, constructor expression instead of constructor name, and field as a pair/object/declaration instead of `id`. B r1 and r3 also add unrequested `Receipt`/`build` keys, a structural violation of “only the specified JSON object.” B r2 is the sole exact pass. Examples: `rust_authored_trait_contract-r1-B/result.json` and `-r2-B/result.json`.
- **Contained optional re-export:** A r1-r3 and B r3 append `::Thing` to the correct `core/src/api.rs` origin; B r1 uses the semantically corresponding Rust module endpoint `core_api::api::Thing`. Those are exact representation failures, not demonstrated wrong-origin retrieval. B r2 is different: despite frozen 8/8 source and 2/2 relation delivery, it reports the entry function (`use_it`, `app/src/lib.rs:3`, parameter `value: core_api::PublicThing`) instead of the re-exported `PublicThing` declaration and its `id: u64` field. That is a genuine final-answer source-comprehension error. See `rust_contained_optional_reexport-r2-B/{result.json,events.json}`.
- **Known call impact:** every answer exactly matches gold. A r1 and r3 still have `task_correct: false` because measurement is incomplete; A r2 and all B attempts have `task_correct: true`. Answer correctness does not establish complete call-proof delivery.
- **Unproven contracts:** every attempt returns all six requested uncertainty booleans correctly as false. Each exact failure is only `src/model.rs::Thing#struct` versus gold `src/model.rs` for `probe_type_origin`. The prompt did not prescribe whether origin includes a symbol endpoint. There is no model false-certainty answer in this case.

The two `invalid_trace` entries are model-supplied `selected_from_search_id` values that do not match an earlier search: `rust_authored_trait_contract-r3-B` adds `?`, and `rust_contained_optional_reexport-r2-A` repeats characters. The adapter correctly returns `selection must reference an earlier search in this run`. These retained tool/trace errors do not show an engine origin or proof error. The authored r3-B attempt remains measurement-complete because the failed call itself reconciles; contained r2-A is incomplete because of separate graph-name mismatches.

## Delivered explore evidence

The frozen relationship scorer records zero forbidden-proven relationships, zero delivery-integrity violations, and zero endpoint issues in all 24 rows. That is direct evidence about the claims it accepted; it does not replace missing complete accounting in the 12 incomplete rows.

- **Origin and configuration:** all three contained-workspace B packets deliver `app/src/lib.rs`, `core/src/api.rs`, `core/src/lib.rs`, root/app/core `Cargo.toml` content, and an `import-resolved` `use_it -> Thing` edge marked `declared_possible`. The scorer maps this proven edge to both required parameter and return meanings, 2/2 each time. `rust_contained_optional_reexport-r1-B/events.json` is the clean representative packet.
- **Trait and impl proof:** authored-contract B packets carry exact `uses_type`, `supertrait`, `impl_self_type`, and, when selected, `impl_trait` records with their source IDs. Coverage is partial: r1 delivers 9/11 meanings and omits both Envelope type meanings; r2 delivers 3/11; r3 delivers 5/11. Their packets disclose `anchor_limit`, `alternative_path`, `cycle`, `hop_limit`, or `unresolved_relation` omissions. The evidence shows incomplete selection, not a forged trait or implementation relationship. See `rust_authored_trait_contract-r1-B/events.json`.
- **Known-call proof:** B r1's locate packet provides no required relationship; B r2 and r3 each provide only the caller's `uses_type -> Config` meaning. No explore packet delivers the definite `caller -> parse` call edge or `parse -> Config` parameter-type meaning. Frozen relation counts are consequently 0/3, 1/3, 1/3. This is a demonstrated compact-workflow relation-coverage limitation even though all three final answers are exact. The packets use `anchor_limit` omissions rather than claiming a false call. See `rust_known_call_impact-r2-B/{events.json,result.json}`.
- **Uncertainty:** each B attempt ultimately delivers only the exact, import-resolved `probe -> src/model.rs::Thing` parameter-type edge, with matching source proof, and earns 1/1. Successful dependency packets disclose two `unresolved_relation` omissions and do not claim exact Choice, Hidden, Display, Generated, Shared, or generic-Thing endpoints. The r3-B first explore request includes unsupported `declared` resolution and is rejected; its subsequent exact/import-resolved request succeeds. The raw evidence therefore shows a retained request error followed by bounded truthful output, not false retrieval. See `rust_unproven_contracts-r3-B/events.json`.

## Cargo control-source boundary

Every Rust case requires one or more Cargo manifest intervals. Arm A misses them in all 12 attempts: authored and known-call A rows deliver 8/9 or 4-5/6, workspace A delivers only the five `.rs` intervals out of eight, and uncertainty A delivers 6/7. Ten actual exact `file` calls across both arms return `File not found in cache`: eight in A (workspace r1 two, r2 one, r3 two; known-call r1 one; uncertainty r2/r3 one each) and two in B (workspace r2, uncertainty r3). The B rows can still receive manifests through explore; B delivers all required manifests except known-call r1, whose locate-only explore packet contains no Cargo source and leaves source at 4/6.

The source path confirms the same mechanism established for Go:

- Frozen `file` dispatch calls `service.get_cached_file` at `benchmarks/typescript_context_adapter.py:206-209`.
- Normal MCP `loci_file` calls the same service at `src/loci/mcp_server.py:470-486`; normal and frozen grep likewise use `grep_repo_result` (`mcp_server.py:488-498`, adapter line 209).
- Graph import/reference records expose `resolution_control_files` as metadata names; they do not return the Cargo file content or its required interval (`src/loci/service.py:1234-1319`). Search, get, and outline are likewise backed by indexed source.
- `get_cached_file` delegates to `IndexStore.get_file_content` (`src/loci/service.py:795-831`), which reads only the mirrored `_sources_dir` (`src/loci/storage/index_store.py:698-729`); grep iterates the same directory (`index_store.py:731-759`). `.rs` is indexable but `.toml` is absent from `EXTENSION_MAP` (`src/loci/parser/languages.py:161-176`) and is classified unsupported (`src/loci/indexability.py:75-91`).
- Explore has a separate Rust-control path: `_is_rust_control_path` recognizes any contained `Cargo.toml`, `_rust_controls` joins it to the index input hash, and `_Source.control` reads the contained repository file then verifies path and SHA-256 before delivering its complete content (`src/loci/exploration.py:287-312,455-494`).

Thus the actual failures demonstrate a product exact-retrieval limitation shared by the benchmark and normal MCP file/grep surfaces, compounded by an asymmetric corpus requirement. Arm A has no published source-content route to satisfy the required Cargo intervals. Explore's successful Cargo delivery is separately hash-checked. This asymmetry prevents treating the source/call comparison as equal-access evidence; it does not demonstrate a Rust resolver wrong origin.

## Accounting and budget limits

Provider usage is present and `token_status: measured` in all 24 rows. Five uncertainty attempts exceed the predeclared 200,000 gross-input-token guard, with exact values shown in the row table; all are retained as `budget_exhausted`. Reported output tokens remain below 8,192 in every row. Observed calls range from 3 to 21, and end-to-end time from 18.97 to 91.74 seconds, below the 24-call and 180-second task bounds. No frozen failure record reports an operation-time, source-byte, task-output-byte, explore-byte, node, selected-item, or neighbor-budget violation.

Complete payload/source byte totals are available for only the 12 measurement-complete rows; their maxima are 17,306 complete-output bytes and 2,296 source bytes, below task limits. The other 12 have null complete-output/source totals because graph calls failed reconciliation. Those nulls stay unavailable. The 20 successful Rust explore packets directly report maxima of 7,553 output bytes, 473 evidence bytes, and eight examined nodes, within explore limits; the rejected r3-B request has no usage packet.

Across the Rust slice, the known graph operation-name defect produces 69 `delivery_trace_mismatch` records and one downstream `unmatched_recorded_delivery` in each of 12 attempts. It makes A 4/12 and B 8/12 evidence-complete and blocks credit for rejected graph-call delivery. The frozen zero relation score for all A rows therefore cannot be interpreted as proof that the engine returned no correct relationships. Ten hidden-pagination errors and the six-seed rejection in uncertainty r1-A are the previously documented schema/adapter boundary defects. None is evidence of a false persisted edge.

## Practical scope

The frozen Rust evidence supports these bounded observations: explore delivered hash-verified Cargo/source evidence in 11/12 B attempts; it gave full required relation coverage for all workspace and uncertainty B attempts; it gave only partial trait and known-call relation coverage; and no accepted packet proves a forbidden origin or invented certainty. One B workspace answer is semantically wrong despite full correct source. Exact file/grep cannot deliver Cargo manifests on either the benchmark or normal MCP surface.

Rust has 0/12 B full passes, 4/12 B exact answers, and only 8/12 B evidence-complete attempts, so the protocol withholds workflow support for this language. The incomplete accounting, unequal Cargo access, partial relation delivery, retained budget failures, and exact-answer-contract ambiguity must remain separate. They provide no final efficiency result and no basis for replacement metrics. Within these 24 rows there is no demonstrated Loci wrong-origin, false-cfg, false-impl, false-call, or incomplete-proof claim; the demonstrated product limitations are control-file access on exact retrieval and incomplete compact relation selection, while the demonstrated independent semantic failure is the model's workspace r2-B answer.
