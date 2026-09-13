# W4.7 Go interim audit

## Scope and evidence

This is a read-only audit of the 24 completed `go_*` rows under `/Users/brummerv/phluxxed/loci-exploration/benchmarks/results/multilingual-context-workflow-v1`: four cases, two arms, and three repetitions. It preserves the frozen results from preparation commit `c910c5ac252a7c982f784d87d61bc4c50fc0c0ec` and freeze commit `14cdf4c3061a74060e51cd7c682b56a40b9f1f9e`. It does not retry, rescore, infer replacement metrics, or make a final efficiency claim.

An attempt name below denotes `<results root>/<attempt>/result.json`; its raw host transcript and adapter ledger are the adjacent `events.json` and `adapter-trace.json`. Prompts, required contexts, relations, forbidden relations, and evaluator-only gold are in `/Users/brummerv/phluxxed/loci-exploration/benchmarks/corpora/multilingual-context-v1/corpus.json:1155-1714`. The agent saw the common prompt and case prompt, plus the workflow guide in Arm B; it did not see gold (`benchmarks/corpora/multilingual-context-v1/corpus.json:11`, `benchmarks/comparisons/multilingual-context-workflow-v1/inputs/comparison-controls.json:57-61`, and `benchmarks/multilingual_context_compare.py:72-80,226-232`).

## Frozen per-case counts

Each case/arm row below accounts for three retained attempts. `Ans`, `Meas`, `Task`, and `Full` count true frozen `answer_correct`, `measurement_complete`, `task_correct`, and `full_pass` fields. `Src=1` counts full context recall. `Rel full` counts equality of delivered and required positive relations; unlike the Python/JavaScript uncertainty cases, the Go uncertainty case requires one positive `Keep -> Request` relation, so no `0/0` rows occur.

| Case | Arm | Rows | Ans | Meas | Task | Full | Src=1 | Rel full |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `go_alias_generic_contract` | A | 3 | 0 | 2 | 0 | 0 | 0 | 0 |
| `go_alias_generic_contract` | B | 3 | 2 | 3 | 2 | 0 | 2 | 0 |
| `go_explicit_embedding` | A | 3 | 1 | 1 | 0 | 0 | 0 | 0 |
| `go_explicit_embedding` | B | 3 | 1 | 2 | 0 | 0 | 3 | 3 |
| `go_known_api_impact` | A | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| `go_known_api_impact` | B | 3 | 3 | 1 | 1 | 0 | 2 | 0 |
| `go_unproven_package_uses` | A | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| `go_unproven_package_uses` | B | 3 | 0 | 0 | 0 | 0 | 3 | 3 |
| **Arm A total** |  | **12** | **4** | **3** | **0** | **0** | **0** | **0** |
| **Arm B total** |  | **12** | **6** | **6** | **3** | **0** | **10** | **6** |
| **Go total** |  | **24** | **10** | **9** | **3** | **0** | **10** | **6** |

No Go row is a full pass. Fifteen rows are measurement-incomplete, including nine Arm A and six Arm B rows. Only nine rows have complete delivery accounting, and no case has all three repetitions measurement-complete in both arms. This slice cannot support a final matched efficiency conclusion.

## Complete failure inventory

These are every category and message retained in `baseline.failures` across the 24 rows:

| Failure | Instances | Rows | Direct classification |
|---|---:|---:|---|
| `delivery_trace_mismatch` | 55 | 15 | Established graph public-name/internal-name evaluator defect |
| `unmatched_recorded_delivery` | 15 | 15 | Derivative aggregate after graph trace events remain unmatched |
| `tool_error` | 26 | 15 | 16 pagination errors, 8 valid-path `go.mod` cache misses, 1 six-seed error, 1 directory-as-file filter error |
| `budget_exhausted` | 1 | 1 | `max_evidence_spans` on one oversized exact `get` |

No `provider_usage_ambiguous` failure appears. All 24 rows retain non-null provider usage with `token_status: measured`. Complete serialized output bytes and source bytes remain null in the 15 measurement-incomplete rows; their retained `recorded_payload_bytes` subtotals are not replacements.

### Established defects

The 55 graph mismatches and 15 derivative unmatched failures are the already documented name-reconciliation defect in `/Users/brummerv/phluxxed/loci-exploration/docs/reviews/2026-09-13-multilingual-measurement-defects.md`. Sixteen `invalid record pagination` errors across 11 rows use limits 50 or 100 against the established hidden maximum 32. The one explicit-ID error is `go_explicit_embedding-r1-A`, whose `graph_retrieve` supplies six seeds against the established hidden maximum five. These errors do not show a bad graph response because the rejected requests never reach one.

### New Go control-file surface mismatch

Eight exact `file` calls use the exact frozen relative path `go.mod` and receive `File not found in cache`: `go_alias_generic_contract-r2-B`, `go_known_api_impact-r3-A`, and all six `go_unproven_package_uses` rows. For example, `go_alias_generic_contract-r2-B/adapter-trace.json` retains attempt 7 with `{"file_path":"go.mod","start_line":1,"end_line":5}`, zero source spans, and the structured error; the same result lists `go.mod` in `provenance.snapshot_files` with hash `01cc905450c59f6d3133f5fd339444536aa4d2b32468f197ea50d39884391d4d` (`go_alias_generic_contract-r2-B/result.json:448`).

This is a real comparison/product-surface mismatch, rather than an invalid model path. The adapter first accepts the path as one of the supplied snapshot files and then delegates to `service.get_cached_file` (`benchmarks/typescript_context_adapter.py:185-207`). The product file call reads only the mirrored source store and raises `FILE_NOT_FOUND` when absent (`src/loci/service.py:795-831`, `src/loci/storage/index_store.py:698-729`). Indexability excludes suffixes outside `EXTENSION_MAP`; `.go` is supported and `.mod` is not (`src/loci/indexability.py:75-91`, `src/loci/parser/languages.py:167`). In contrast, explore explicitly recognizes `go.mod` and `go.work` controls and selects them from indexed input hashes (`src/loci/exploration.py:455-482`). Actual B explore packets consequently can and do deliver `go.mod` evidence.

The frozen corpus requires a `module` context in every Go case (`corpus.json:1233`, `:1387`, `:1531`, `:1656`). All 12 Arm A rows miss exactly that context; ten of twelve Arm B rows deliver it, with only `go_alias_generic_contract-r3-B` and `go_known_api_impact-r2-B` missing it. The eight direct failures demonstrate the unavailable exact-file route. They do not alone prove that every other module omission was caused by that route, because some attempts did not request `file("go.mod")`. The defect is therefore scoped to required control-file access and an arm-asymmetric tool surface, not to incorrect Go module resolution, fabricated source, or a replacement outcome.

#### Normal MCP versus frozen benchmark clarification

The cache limitation is not confined to the evaluator adapter. Normal MCP `loci_file` calls `service.get_cached_file(..., ensure_fresh=True)` at `src/loci/mcp_server.py:470-486`, the same service function used by frozen benchmark `file` at `benchmarks/typescript_context_adapter.py:205-207`. Refreshing does not expand the supported-source mirror: `get_cached_file` reads `IndexStore.get_file_content`, which reads only `_sources_dir`, and `.mod` remains excluded by `src/loci/indexability.py:75-91`. The eight frozen calls directly demonstrate the failure in the benchmark transport; the shared source call path establishes that normal MCP `loci_file` has the same cache-only limitation for `go.mod`.

Neither normal nor frozen grep is an alternate full-control reader. Normal MCP `loci_grep` calls `service.grep_repo_result` at `src/loci/mcp_server.py:488-498`; frozen `grep` calls the same service at `benchmarks/typescript_context_adapter.py:208-209`; and `IndexStore.grep_files` enumerates only `_sources_dir` at `src/loci/storage/index_store.py:731-759`. Normal grep at least reports bounded indexed-source coverage, but it cannot return bytes from an unsupported `.mod` file.

No other published Arm A tool returns the full control file. Search, outline, and get are indexed-symbol/source operations, while `go.mod` is not an indexable source file. Graph record responses may name `go.mod` in `resolution_control_files`; for example, `service.graph_imports` serializes that filename at `src/loci/service.py:1234-1319`, but it does not return the control content or an `evidence_span`. The frozen adapter credits graph source only from content-bearing `evidence_span` values or indexed signature spans (`benchmarks/typescript_context_adapter.py:103-167`). Internally, Go indexing can read the control and retain its hash, but that is not an agent-visible full-file read.

Consequently, within the frozen published tools, only Arm B's added `loci_explore` can deliver the exact full `go.mod` control span. Arm A has no published route that can satisfy the corpus's required `module` source interval. This makes the comparison defect precise: normal product exact `file`/`grep` also lack non-indexed Go-control retrieval, while the evaluator compounds that product-surface limitation by requiring the control interval in both arms even though only B receives the special control-evidence route. This conclusion is source-established; no normal-MCP runtime reproduction or result replacement is asserted.

The remaining isolated tool errors are caller requests: `go_known_api_impact-r3-B` passes directory `api` as a `search.file_paths` entry where the adapter requires an exact supplied file, and the six-seed call above exceeds the known hidden anchor bound. Neither is evidence of wrong returned source.

### Budget and usage

`go_unproven_package_uses-r3-A` exceeds `max_evidence_spans` on attempt 2 by requesting ten symbol IDs with context 20 in one `get`. The adapter retains a budget-exhausted error and withholds source for that attempt. This row also has graph reconciliation failures, so no independent output/accounting completion can be inferred. No Go row exceeds the task-time or provider-input-token limits, and no provider-usage gap is recorded.

## Source, relationships, proof, and forbidden origin

Every required positive Go relation is marked available in every row: 5/5 for alias/generic, 4/4 for embedding, 5/5 for API impact, and 1/1 for the uncertainty case. Across all 24 frozen relationship objects, `missing_endpoints`, `multiple_endpoints`, `source_only_endpoints`, `endpoint_issues`, `forbidden_available_relationships`, `forbidden_delivered_relationships`, `forbidden_proven_relationships`, and `delivery_integrity_violations` are all empty or zero. Thus the retained index-side evidence shows no missing gold edge, forbidden indexed edge, wrong-origin delivered proof, hash/span failure, or invented relationship.

That absence has a completeness boundary. The nine measurement-complete rows certify their full delivery accounting; the other 15 do not because of the graph reconciler, and their null complete-output/source totals remain null. Individually reconciled explore packets remain directly observable, but they do not promote an incomplete row.

The Arm B relation patterns are supported by the actual packets in adjacent `events.json` files:

- `go_alias_generic_contract-r1-B` and `-r2-B` deliver 4/5. The explicit Build traversal returns Build-to-AliasID, Build-to-Page, Build-to-UserID, and Page-to-Number, and reports one `alternative_path` plus two `unresolved_relation` omissions (`r1-B/events.json:120-473`). The persisted AliasID-to-UserID edge remains available but is omitted because UserID is already selected directly from Build. This is disclosed compact-selection coverage, not an engine-missing or wrong-origin edge. `r3-B` uses only inferred `locate`, whose declared relationship scope is `none`, reports `anchor_limit: 5`, and delivers 0/5; that is a workflow/intent choice.
- All three embedding B rows deliver 4/4 through explicit seeded `type_dependencies`: both Start parameter types and both `embeds` edges. `r2-B` first selects Stamp via an inferred query and reports an anchor limit, then the explicit Start call supplies full gold relation proof. This is positive evidence that Go struct and interface embedding are present with valid source proof.
- `go_known_api_impact-r1-B` delivers 3/5: inferred dependencies supplies Handle-to-Request, and explicit impact supplies both known call edges while reporting two `alternative_path` omissions (`r1-B/events.json:31-836`). `r3-B` uses locate plus impact and delivers the two calls but none of the three parameter-type edges. `r2-B` seeds Handle and Request with `dependencies`; it returns zero relations and reports one `alternative_path`, then never invokes impact, so it delivers 0/5. These are intent/seed/compact-selection coverage differences. The index still marks every gold edge available.
- Every uncertainty B row delivers the sole positive Keep-to-Request type edge. The explore packets return no Probe/Missing call relationship and explicitly report eight `unresolved_relation` omissions; see `go_unproven_package_uses-r2-B/events.json:476-552`. This is fail-closed engine behavior for shadowed, ambiguous, external, and missing endpoints.

Some attempts inspect `wrong/model.go`, including all three uncertainty A rows and two uncertainty B rows. Reading a deliberate decoy is not a provenance claim. No answer assigns `Keep` or `Build` to `wrong/model.go`, no explore packet proves an edge to it, and every forbidden/proof-integrity field remains clear.

## Answer interpretation against the visible prompts

The frozen exact scores remain authoritative, but exact mismatch does not always imply factual misunderstanding. The prompts name output fields and explicitly define some pairs and arrays; they do not uniformly specify name-only versus signature-bearing values, module import path versus repository filepath, or an empty flat array versus status-rich per-use objects. The following distinctions preserve that limit.

### Exact-contract representation differences

- All three alias/generic A answers report `model_origin: "example.com/acme/model"` rather than evaluator gold `model/model.go`; `r2-B` does the same and reports `page_field: "Value T"` rather than `Value`. The package path is the actual authored import origin, and `Value T` is the actual field declaration. The prompt at `corpus.json:1161` does not specify filepath-only or name-only encoding. These are exact-contract mismatches, not demonstrated wrong-source facts. `r1-B` and `r3-B` exactly match gold.
- Embedding `r2-B` and `r3-B` report `audit_field: "Created int64"` and `runner_method: "Run() error"` instead of name-only `Created` and `Run`. Both retain the correct authored field and signature. `r1-A` also uses the signature-bearing method form. These value-granularity differences are not factual errors.
- All six uncertainty answers place the four unproven uses into an array or per-caller object with explicit statuses such as `missing`, `shadowed`, `external`, and `ambiguous`, whereas evaluator gold requires `exact_probe_or_missing_callees: []`. They also express the correct Keep origin as a package-qualified value or symbol ID instead of the gold filepath. The prompt at `corpus.json:1596` asks to report the field while preserving each unresolved category but does not disclose the flat empty-array gold shape. These are exact-contract representation failures. The status labels explicitly avoid claiming the listed calls are proven, and every answer correctly says the old module proof does not survive.

### Demonstrated semantic false certainty

`go_explicit_embedding-r1-A/result.json:602-614` and `go_explicit_embedding-r2-A/result.json` set `promoted_call_proven: true`. The visible prompt expressly asks whether embedding alone proves the target of `e.Stamp()` (`corpus.json:1315`), and frozen gold is false (`:1451`). These two rows demonstrate model false certainty. The engine does not share that error: the corpus forbids the promoted call, no explore packet returns it, and all forbidden-proven counts remain zero.

All six `go_known_api_impact` answers exactly match gold. Their failures arise from source, relation, tool-accounting, or delivery gates rather than answer facts. No other Go answer in this slice demonstrates a wrong repository origin or a wrong authored field/type once evaluator-only representation conventions are separated from factual content.

## Row-level accounting appendix

`G` is graph delivery mismatch, `U` unmatched-recorded aggregate, `P` pagination error, `F` valid `go.mod` cache miss, `I` explicit-seed bound, `S` invalid directory-as-file search filter, and `B` evidence-span budget failure.

| Attempt | Ans | Meas | Task | Full | Source | Relations | Failures |
|---|---:|---:|---:|---:|---:|---:|---|
| `go_alias_generic_contract-r1-A` | 0 | 1 | 0 | 0 | 7/8 | 0/5 | none |
| `go_alias_generic_contract-r1-B` | 1 | 1 | 1 | 0 | 8/8 | 4/5 | none |
| `go_alias_generic_contract-r2-A` | 0 | 0 | 0 | 0 | 7/8 | 0/5 | G2 U1 |
| `go_alias_generic_contract-r2-B` | 0 | 1 | 0 | 0 | 8/8 | 4/5 | F1 |
| `go_alias_generic_contract-r3-A` | 0 | 1 | 0 | 0 | 7/8 | 0/5 | none |
| `go_alias_generic_contract-r3-B` | 1 | 1 | 1 | 0 | 7/8 | 0/5 | none |
| `go_explicit_embedding-r1-A` | 0 | 0 | 0 | 0 | 7/8 | 0/4 | I1 G3 U1 |
| `go_explicit_embedding-r1-B` | 1 | 0 | 0 | 0 | 8/8 | 4/4 | P2 G3 U1 |
| `go_explicit_embedding-r2-A` | 0 | 1 | 0 | 0 | 7/8 | 0/4 | none |
| `go_explicit_embedding-r2-B` | 0 | 1 | 0 | 0 | 8/8 | 4/4 | none |
| `go_explicit_embedding-r3-A` | 1 | 0 | 0 | 0 | 7/8 | 0/4 | G1 U1 |
| `go_explicit_embedding-r3-B` | 0 | 1 | 0 | 0 | 8/8 | 4/4 | none |
| `go_known_api_impact-r1-A` | 1 | 0 | 0 | 0 | 7/8 | 0/5 | P2 G4 U1 |
| `go_known_api_impact-r1-B` | 1 | 0 | 0 | 0 | 8/8 | 3/5 | P1 G2 U1 |
| `go_known_api_impact-r2-A` | 1 | 0 | 0 | 0 | 7/8 | 0/5 | P1 G2 U1 |
| `go_known_api_impact-r2-B` | 1 | 0 | 0 | 0 | 7/8 | 0/5 | P1 G5 U1 |
| `go_known_api_impact-r3-A` | 1 | 0 | 0 | 0 | 7/8 | 0/5 | F1 G2 U1 |
| `go_known_api_impact-r3-B` | 1 | 1 | 1 | 0 | 8/8 | 2/5 | S1 |
| `go_unproven_package_uses-r1-A` | 0 | 0 | 0 | 0 | 6/7 | 0/1 | P2 F1 G7 U1 |
| `go_unproven_package_uses-r1-B` | 0 | 0 | 0 | 0 | 7/7 | 1/1 | P1 F1 G4 U1 |
| `go_unproven_package_uses-r2-A` | 0 | 0 | 0 | 0 | 6/7 | 0/1 | F1 P1 G6 U1 |
| `go_unproven_package_uses-r2-B` | 0 | 0 | 0 | 0 | 7/7 | 1/1 | P2 F1 G3 U1 |
| `go_unproven_package_uses-r3-A` | 0 | 0 | 0 | 0 | 6/7 | 0/1 | B1 P1 F1 G6 U1 |
| `go_unproven_package_uses-r3-B` | 0 | 0 | 0 | 0 | 7/7 | 1/1 | F1 P2 G5 U1 |

The appendix sums to 24 rows, 10 exact answers, 9 complete measurements, 3 task-correct rows, 0 full passes, 55 `G`, 15 `U`, 16 `P`, 8 `F`, 1 `I`, 1 `S`, and 1 `B`, matching the aggregate inventory.

## Report-safe Go interpretation

The Go evidence supports three bounded findings. First, the frozen index contains all required Go relations and actual explore packets demonstrate valid alias/generic, embedding, call-impact, and fail-closed uncertainty proof without a forbidden or integrity violation. Second, compact selection and workflow choices omit available alternate/type paths in the alias and impact cases; those omissions are disclosed and remain failed relation gates. Third, the exact file surface cannot return required `go.mod` controls even though they belong to the frozen snapshot and explore can deliver them, creating a demonstrated comparison/tool-surface asymmetry.

The slice does not demonstrate an engine wrong-origin, invented-source, or false-certainty retrieval defect. It does demonstrate model false certainty about promoted Go method dispatch in two Arm A answers. No incomplete row is promoted, no null accounting field is replaced, and no Go efficiency claim is available before the full 114-row replay/report.
