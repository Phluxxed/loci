# R0.5 demand-driven semantics design challenge

Recommendation: proceed with the isolated experiment. Reuse the existing extractors and resolvers behind a lazy semantic-context request, but do not treat a sparse input set as a complete resolution universe. A small proof closure is plausible; a small reverse-discovery cost is not established. No new generic graph or production API is needed.

## Correct the causal framing

The frozen Anvil source places `compilerRetrievalLimits` in `src/brain-context/render.ts`. Its first lines import `BrainRetrievalResult` and `BrainCompiledEvidence` directly from `./retrieve.ts`, and the function parameter is `retrieval: BrainRetrievalResult`. The prompt explicitly asks about imported contracts. Thus the five missed `retrieve.ts` spans are reachable through forward imported-contract acquisition. Recovering them does not demonstrate that reverse caller semantics was necessary. Report the actual successful route from the request trace. This distinction does not change the fixed source or proof scores.

The frozen Rust workspace case genuinely crosses `app/src/lib.rs` -> optional inherited Cargo dependency -> `core/src/lib.rs` reexport -> `core/src/api.rs`. Workspace, app and core Cargo controls matter. `wrong.rs` is not a substitute for the declared module route. Preserve `declared_possible` and do not infer an active build.

## Minimum sound closure

1. Keep a complete admitted filename/hash inventory for path-resolution candidates. `graph/imports.py:432` derives Python/JavaScript candidates from supplied `file_nodes`; a subset can remove competing candidates. File-only nodes for the whole admitted inventory are acceptable, charged discovery work, not whole-repository declaration parsing. Record excluded/inaccessible paths and never call this repository-exhaustive.
2. Parse each selected file completely, not only matched lines or named declarations. `graph/calls.py:558` builds callable/type-member maps from supplied symbols; `graph/references.py:472` builds complete export surfaces and lexical source ownership from supplied symbols/imports/exports. Truncated file observations can erase shadowing or competing declarations.
3. Before accepting an imported reference, recursively parse its local import/export proof closure. Include every alternative reexport, especially star exports; parsing only the branch that yielded a match can turn ambiguity into a false unique endpoint. `_javascript_references.py:87` propagates ambiguity and star failures; `:432` accepts a unique surface target from that index, which is only as complete as its inputs. Unparsed competing branches mean unresolved/partial, not resolved.
4. Load relevant existing language controls against the full admitted inventory, with all work charged. For Rust, collect complete module-declaration closure from roots of touched crates, including every conditional alternative and contained dependency needed by the route. `_rust_resolution.py:903` traverses module observations from the root; missing observations silently remove routes. A simple complete touched-crate module closure is safer than inventing a new route-pruning resolver. If this expands to most of a crate, report that cost honestly.
5. A whole-repository text scan can select candidate callers, but direct target spelling does not discover every alias or reexport. Either extend reverse candidate discovery through observed alias/import routes to a fixed point, charging each scan, or explicitly retain non-exhaustive reverse coverage. Sound individual edges do not require proof that every caller was discovered. The bounded experiment need not implement general exhaustive reverse discovery.
6. Existing call resolution joins exact references and local declarations (`calls.py:558`), so selected-file proof can avoid repository-wide semantic materialization when the above closure holds. Emit sparse proof records and their supporting source/control extents. Unsupported type families remain unsupported even if importing their source improves source coverage.

The smallest safe implementation may simply close all local imports/exports from selected files and all module declarations in touched Rust crates. Do not optimize this closure during R0.5 unless measurements show that it prevents the requested comparison. Broad closure is a valid negative result for the cost hypothesis.

## Prospective question and follow-up policy

Freeze one generic semantic-context request for contract/dependency questions, seeded by the original entry query or an actually observed identity. Permit bounded bidirectional import/reference/call context; explicit impact questions may request known callers. Derive request kind from authored prompt/question-kind using fixed rules. Do not branch on case ID, gold context, gold edge IDs, expected five spans, or scores.

A direct imported-contract route should be eligible before reverse caller expansion. Follow-up source requests may use only paths/identities in already delivered source or semantic packets. Related endpoint source is acquisition evidence; it is not automatically semantic proof for every declaration in that file. Keep packet-linked proof, same-session proof, source acquisition and task-answer success separate.

Apply the same logical request opportunity and shared request/output/source budgets to R0.3, R0.4 and demand semantics. R0.3 uses retained context capability; R0.4 performs its frozen lexical fallback or reports unsupported relationships. If adding a generic follow-up policy improves R0.4, rerun and label that policy change rather than compare against stale R0.4 totals. Avoid granting the candidate an uncharged extra semantic call. Record the original R0.4 comparison separately if needed.

## Freshness, isolation and measurements

A temporary immutable copy of admitted bytes is a reasonable adapter for path-based parsers. Copy only safely read bytes, preserve their hashes and verify freshness before delivery/cache reuse. Charge full inventory/hash reads, copy writes/bytes, discovery scans, control loading, parsing, resolution, proof construction, source delivery and cache validation. Count transient parsed-file count, bytes, peak state and snapshot storage, not merely final persisted store size.

Cache sparse results by full source-and-control inventory identity. Changes in import alternatives, ignored membership, Cargo controls or a newly added file must invalidate affected cached conclusions. A source-only path must not initialize parser/resolver state. Report cold first request, repeated same question and any cross-question amortization separately; a repeat in a fresh worker is not a warm cache measurement. Do not exclude global work just because it happens before a timed semantic method.

## Focused acceptance evidence and stop boundary

Retain checks that demonstrate lazy source-only behavior, one local accepted call/reference, a competing export/module alternative that prevents false unique resolution, optional Cargo configuration mutation, and cache invalidation after adding a competing file. These test the new seam; do not require a new language engine. Existing frozen uncertainty cases should retain honest unsupported/ambiguous/private/external outcomes. No fixed-source success warrants claiming general caller completeness or active Rust configuration.

After targeted recovery and the authorized comparison, stop with the supported architectural conclusion, including a negative cost finding. No production integration, broader model campaign or generic semantic framework follows automatically.

## Inspection provenance and limitation

Read current R0.5 resolver sources, the retained architecture request/score adapter, authored prompts and the relevant frozen Rust/Anvil source bytes. Historical R0.4 memory supplied comparison context only; current sources support the design findings. One normal Loci retrieval of candidate `src/loci/graph/calls.py` was issued before the parent sent the direct-read-only constraint. It may have populated an ambient candidate index; parent was notified immediately. All later inspection was direct read-only. This retrieval is design inspection, not an experimental measurement or candidate implementation path; isolated benchmark stores still require their own clean setup.
